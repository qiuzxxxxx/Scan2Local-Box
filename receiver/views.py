import hashlib
import ipaddress
import json
import mimetypes
import os
import re
import secrets
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.parse
import zipfile
import xml.etree.ElementTree as ET
from html import escape
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.http import FileResponse, Http404, HttpResponse, HttpResponseForbidden, JsonResponse, StreamingHttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .models import Device, TransferRecord, UploadRecord
from .qr import svg

CURRENT_TRANSFER_TOKEN = settings.TRANSFER_TOKEN
CURRENT_HOST = None
NETWORK_CACHE = {"until": 0, "addresses": []}
PREVIEW_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp",
    ".mp4", ".webm", ".mp3", ".wav", ".ogg", ".m4a",
    ".pdf", ".docx", ".txt", ".md", ".csv", ".json", ".log",
}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".log"}


def local_ip():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("192.0.2.1", 80))
        address = sock.getsockname()[0]
        if not address.startswith(("127.", "169.254.")):
            return address
    except OSError:
        pass
    finally:
        sock.close()
    try:
        for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            address = item[4][0]
            if not address.startswith(("127.", "169.254.")):
                return address
    except OSError:
        pass
    return "127.0.0.1"


def current_host():
    return CURRENT_HOST or local_ip()


def network_addresses(force=False):
    now = time.monotonic()
    if not force and NETWORK_CACHE["until"] > now:
        return list(NETWORK_CACHE["addresses"])
    found = []
    default_ip = local_ip()

    def add(address, label):
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError:
            return
        if parsed.version != 4 or parsed.is_loopback or parsed.is_link_local or parsed.is_unspecified:
            return
        if not parsed.is_private:
            return
        if not any(item["ip"] == str(parsed) for item in found):
            found.append({"ip": str(parsed), "label": label or "网络适配器"})

    try:
        output = subprocess.run(
            ["ipconfig"], capture_output=True, text=True, errors="replace", timeout=3, check=False
        ).stdout
        for block in re.split(r"\r?\n\s*\r?\n", output):
            match = re.search(r"IPv4[^\r\n:]*:\s*([0-9.]+)", block)
            if not match:
                continue
            lines = [line.strip() for line in block.splitlines() if line.strip()]
            add(match.group(1), lines[0].rstrip(":") if lines else "网络适配器")
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            add(item[4][0], "本机网络")
    except OSError:
        pass
    if default_ip != "127.0.0.1":
        add(default_ip, "系统当前使用的网络")
        found.sort(key=lambda item: item["ip"] != default_ip)
    NETWORK_CACHE["addresses"] = found
    NETWORK_CACHE["until"] = now + 15
    return list(found)


def authorized(request):
    supplied = request.GET.get("token", "")
    return bool(supplied and secrets.compare_digest(supplied, CURRENT_TRANSFER_TOKEN))


def is_local_admin(request):
    return request.META.get("REMOTE_ADDR") in {"127.0.0.1", "::1"}


def device_for(request, update=False):
    raw_key = request.headers.get("X-Device-Key") or request.GET.get("device", "")
    if not raw_key:
        return None
    digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    device = Device.objects.filter(key_hash=digest, is_active=True).first()
    if device and update:
        device.last_seen = timezone.now()
        device.save(update_fields=["last_seen"])
    return device


def allowed_client(request):
    return is_local_admin(request) or device_for(request) is not None


def home(request):
    if "token" in request.GET:
        if not authorized(request):
            return HttpResponseForbidden("二维码已失效，请重新打开电脑上的页面扫码。")
    elif not is_local_admin(request):
        return HttpResponseForbidden("请在电脑上打开本地收件箱页面，再用手机扫码连接。")
    address = "http://{}:{}{}".format(
        current_host(), request.get_port(),
        "/?token=" + urllib.parse.quote(CURRENT_TRANSFER_TOKEN),
    )
    return render(request, "index.html", {
        "transfer_token": CURRENT_TRANSFER_TOKEN,
        "share_address": address,
        "is_admin": is_local_admin(request) and "token" not in request.GET,
    })


def qr_image(request):
    if not is_local_admin(request) and not authorized(request):
        return HttpResponseForbidden("Forbidden")
    address = "http://{}:{}{}".format(
        current_host(), request.get_port(),
        "/?token=" + urllib.parse.quote(CURRENT_TRANSFER_TOKEN),
    )
    return HttpResponse(svg(address), content_type="image/svg+xml")


@csrf_exempt
@require_POST
def refresh_link(request):
    if not is_local_admin(request):
        return HttpResponseForbidden("请在电脑本机刷新连接二维码。")
    global CURRENT_TRANSFER_TOKEN
    global CURRENT_HOST
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({"error": "网络地址格式不正确。"}, status=400)
    selected_ip = str(data.get("ip", "")).strip()
    if selected_ip:
        available = {item["ip"] for item in network_addresses(force=True)}
        if selected_ip not in available:
            return JsonResponse({"error": "这个地址不在本机网络适配器中，请刷新网络列表。"}, status=400)
        CURRENT_HOST = selected_ip
    CURRENT_TRANSFER_TOKEN = secrets.token_urlsafe(18)
    address = "http://{}:{}{}".format(
        current_host(), request.get_port(),
        "/?token=" + urllib.parse.quote(CURRENT_TRANSFER_TOKEN),
    )
    return JsonResponse({
        "shareAddress": address,
        "qrUrl": "/qr.svg?token=" + urllib.parse.quote(CURRENT_TRANSFER_TOKEN),
        "activeAddress": current_host(),
    })


def files(request):
    if not allowed_client(request):
        return JsonResponse({"error": "请通过电脑上的二维码连接此设备。"}, status=403)
    query = request.GET.get("q", "").strip()[:180]
    sort = request.GET.get("sort", "newest")
    ordering = {
        "newest": ("-uploaded_at", "-id"),
        "oldest": ("uploaded_at", "id"),
        "name-asc": ("original_name", "-id"),
        "name-desc": ("-original_name", "-id"),
        "largest": ("-file_size", "-id"),
        "smallest": ("file_size", "-id"),
    }.get(sort, ("-uploaded_at", "-id"))
    try:
        page = max(int(request.GET.get("page", "1")), 1)
    except ValueError:
        page = 1
    page_size = 100
    records = UploadRecord.objects.all()
    if query:
        records = records.filter(original_name__icontains=query)
    total_count = records.count()
    page_count = (total_count + page_size - 1) // page_size
    page = min(page, max(page_count, 1))
    records = records.order_by(*ordering)[(page - 1) * page_size:page * page_size]
    result = []
    for record in records:
        extension = Path(record.original_name).suffix.lower()
        uploaded = timezone.localtime(record.uploaded_at)
        preview_kind = (
            "image" if extension in IMAGE_EXTENSIONS else
            "pdf" if extension == ".pdf" else
            "word" if extension == ".docx" else
            "text" if extension in TEXT_EXTENSIONS else
            "media"
        )
        result.append({
            "id": record.id,
            "name": record.original_name,
            "storedName": record.stored_name,
            "size": record.file_size,
            "modified": uploaded.isoformat(timespec="seconds"),
            "previewable": extension in PREVIEW_EXTENSIONS,
            "previewKind": preview_kind,
        })
    return JsonResponse({
        "files": result,
        "totalCount": total_count,
        "page": page,
        "pageSize": page_size,
        "pageCount": page_count,
    })


@require_GET
def storage_status(request):
    if not allowed_client(request):
        return JsonResponse({"error": "请先连接电脑后查看存储空间。"}, status=403)
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(settings.UPLOAD_DIR)
    total = UploadRecord.objects.aggregate(total=Sum("file_size"))["total"] or 0
    return JsonResponse({
        "fileCount": UploadRecord.objects.count(),
        "usedBytes": total,
        "diskFreeBytes": usage.free,
        "diskTotalBytes": usage.total,
    })


def requested_file_ids(request):
    try:
        data = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, JsonResponse({"error": "请求格式不正确。"}, status=400)
    raw_ids = data.get("ids") if isinstance(data, dict) else None
    if not isinstance(raw_ids, list) or not raw_ids:
        return None, JsonResponse({"error": "请选择要处理的文件。"}, status=400)
    if any(not isinstance(item, int) or isinstance(item, bool) or item <= 0 for item in raw_ids):
        return None, JsonResponse({"error": "文件列表中包含无效项目。"}, status=400)
    ids = list(dict.fromkeys(raw_ids))
    if len(ids) > 100:
        return None, JsonResponse({"error": "一次最多处理 100 个文件。"}, status=400)
    return ids, None


@csrf_exempt
@require_POST
def download_files_zip(request):
    if not allowed_client(request):
        return JsonResponse({"error": "请先连接已授权设备。"}, status=403)
    ids, error_response = requested_file_ids(request)
    if error_response:
        return error_response
    records_by_id = {record.id: record for record in UploadRecord.objects.filter(id__in=ids)}
    if len(records_by_id) != len(ids):
        return JsonResponse({"error": "部分文件已不存在，请刷新文件库后重试。"}, status=404)
    records = [records_by_id[file_id] for file_id in ids]
    paths = []
    for record in records:
        if Path(record.stored_name).name != record.stored_name:
            return JsonResponse({"error": "文件记录无效，无法打包下载。"}, status=400)
        target = settings.UPLOAD_DIR / record.stored_name
        if not target.is_file():
            return JsonResponse({"error": "文件“{}”已不在磁盘上。".format(record.original_name)}, status=404)
        paths.append(target)

    estimated_archive_size = sum(record.file_size for record in records) + len(records) * 256 + 65536
    temporary_directory = tempfile.gettempdir()
    if estimated_archive_size > shutil.disk_usage(temporary_directory).free:
        return JsonResponse({"error": "临时磁盘空间不足，无法创建 ZIP 文件。"}, status=507)
    archive_file = tempfile.SpooledTemporaryFile(
        max_size=16 * 1024 * 1024, mode="w+b", dir=temporary_directory
    )
    used_names = set()
    try:
        with zipfile.ZipFile(archive_file, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
            for record, target in zip(records, paths):
                archive_name = record.original_name
                if archive_name.casefold() in used_names:
                    stem, suffix = os.path.splitext(archive_name)
                    index = 2
                    while "{} ({}){}".format(stem, index, suffix).casefold() in used_names:
                        index += 1
                    archive_name = "{} ({}){}".format(stem, index, suffix)
                used_names.add(archive_name.casefold())
                archive.write(target, arcname=archive_name)
        archive_file.seek(0, os.SEEK_END)
        archive_size = archive_file.tell()
        archive_file.seek(0)
    except OSError:
        archive_file.close()
        return JsonResponse({"error": "打包失败，请检查磁盘空间和文件状态。"}, status=507)

    archive_name = "本地收件箱-{}个文件.zip".format(len(records))
    device = device_for(request, update=True)
    if device:
        transfer = TransferRecord.objects.create(
            direction=TransferRecord.PC_TO_PHONE,
            status=TransferRecord.TRANSFERRING,
            file_name=archive_name,
            file_size=archive_size,
            device=device,
            device_name=device.name,
        )

        def stream_archive():
            transferred = 0
            completed = False
            try:
                while True:
                    chunk = archive_file.read(64 * 1024)
                    if not chunk:
                        break
                    yield chunk
                    transferred += len(chunk)
                    if transferred % (1024 * 1024) < len(chunk):
                        TransferRecord.objects.filter(pk=transfer.pk).update(transferred_size=transferred)
                completed = True
            finally:
                archive_file.close()
                TransferRecord.objects.filter(pk=transfer.pk).update(
                    transferred_size=transferred,
                    status=TransferRecord.COMPLETED if completed else TransferRecord.INTERRUPTED,
                )

        response = StreamingHttpResponse(stream_archive(), content_type="application/zip")
        response._resource_closers.append(archive_file.close)
        response["Content-Length"] = str(archive_size)
    else:
        response = FileResponse(archive_file, content_type="application/zip")
    response["Content-Disposition"] = "attachment; filename*=UTF-8''" + urllib.parse.quote(archive_name)
    response["X-Content-Type-Options"] = "nosniff"
    return response


@csrf_exempt
@require_POST
def delete_files_batch(request):
    if not allowed_client(request):
        return JsonResponse({"error": "请先连接已授权设备。"}, status=403)
    ids, error_response = requested_file_ids(request)
    if error_response:
        return error_response
    records_by_id = {record.id: record for record in UploadRecord.objects.filter(id__in=ids)}
    if len(records_by_id) != len(ids):
        return JsonResponse({"error": "部分文件已不存在，请刷新文件库后重试。"}, status=404)
    deleted_ids = []
    failed = []
    for file_id in ids:
        record = records_by_id[file_id]
        target = settings.UPLOAD_DIR / record.stored_name
        try:
            if target.exists():
                target.unlink()
            record.delete()
            deleted_ids.append(file_id)
        except OSError:
            failed.append({"id": file_id, "name": record.original_name})
    return JsonResponse({"deletedIds": deleted_ids, "failed": failed})


def transfer_history(request):
    if is_local_admin(request):
        records = TransferRecord.objects.all()
    else:
        device = device_for(request)
        if not device:
            return JsonResponse({"error": "请先连接电脑后查看传输记录。"}, status=403)
        records = TransferRecord.objects.filter(device=device)
    result = []
    for record in records.select_related("device")[:100]:
        percent = 100 if record.status == TransferRecord.COMPLETED else (
            round(record.transferred_size * 100 / record.file_size) if record.file_size else 0
        )
        result.append({
            "id": record.id,
            "direction": record.direction,
            "directionLabel": record.get_direction_display(),
            "status": record.status,
            "statusLabel": record.get_status_display(),
            "name": record.file_name,
            "size": record.file_size,
            "transferred": record.transferred_size,
            "percent": min(percent, 100),
            "deviceName": record.device.name if record.device_id else record.device_name,
            "createdAt": timezone.localtime(record.created_at).isoformat(timespec="seconds"),
        })
    return JsonResponse({"records": result})


@csrf_exempt
@require_POST
def rename_file(request, upload_id):
    if not allowed_client(request):
        return JsonResponse({"error": "请先连接已授权设备。"}, status=403)
    try:
        data = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({"error": "请求格式不正确。"}, status=400)
    raw_name = str(data.get("name", "")).strip()
    if not raw_name or "/" in raw_name or "\\" in raw_name:
        return JsonResponse({"error": "请输入有效文件名，不要包含路径。"}, status=400)
    new_name = clean_filename(raw_name)
    if len(new_name) > 180:
        return JsonResponse({"error": "文件名不能超过 180 个字符。"}, status=400)
    record = UploadRecord.objects.filter(id=upload_id).first()
    if not record:
        return JsonResponse({"error": "文件记录不存在。"}, status=404)
    old_path = settings.UPLOAD_DIR / record.stored_name
    if not old_path.is_file():
        return JsonResponse({"error": "磁盘上找不到这个文件。"}, status=404)
    prefix = record.stored_name.partition("__")[0]
    new_stored_name = prefix + "__" + new_name
    new_path = settings.UPLOAD_DIR / new_stored_name
    if new_path != old_path and new_path.exists():
        return JsonResponse({"error": "目标文件名已存在，请换一个名字。"}, status=409)
    if new_path == old_path:
        return JsonResponse({"message": "文件名没有变化。", "name": new_name})
    old_name = record.original_name
    try:
        os.replace(old_path, new_path)
        try:
            with transaction.atomic():
                record.original_name = new_name
                record.stored_name = new_stored_name
                record.save(update_fields=["original_name", "stored_name"])
        except Exception:
            os.replace(new_path, old_path)
            raise
    except OSError:
        return JsonResponse({"error": "重命名失败，请检查文件是否正被其他程序占用。"}, status=500)
    except Exception:
        return JsonResponse({"error": "数据库更新失败，已尝试恢复原文件名。"}, status=500)
    return JsonResponse({"message": "文件已重命名。", "name": new_name, "oldName": old_name})


@csrf_exempt
@require_POST
def replace_file(request, upload_id):
    if not allowed_client(request):
        return JsonResponse({"error": "请先连接已授权设备。"}, status=403)
    record = UploadRecord.objects.filter(id=upload_id).first()
    if not record:
        return JsonResponse({"error": "文件记录不存在。"}, status=404)
    replacement = request.FILES.get("file")
    if not replacement:
        return JsonResponse({"error": "请选择要替换的文件。"}, status=400)
    if replacement.size > settings.MAX_UPLOAD_BYTES:
        return JsonResponse({"error": "替换文件不能超过 250 MB。"}, status=413)
    old_ext = Path(record.original_name).suffix.lower()
    new_ext = Path(replacement.name).suffix.lower()
    if old_ext != new_ext:
        return JsonResponse({"error": "替换文件需保持原扩展名（{}）。".format(old_ext or "无扩展名")}, status=400)
    target = settings.UPLOAD_DIR / record.stored_name
    if not target.is_file():
        return JsonResponse({"error": "磁盘上找不到这个文件。"}, status=404)
    temporary = settings.UPLOAD_DIR / (".replace-" + secrets.token_hex(8) + ".tmp")
    backup = settings.UPLOAD_DIR / (".backup-" + secrets.token_hex(8) + ".tmp")
    try:
        with temporary.open("wb") as destination:
            for chunk in replacement.chunks():
                destination.write(chunk)
        os.replace(target, backup)
        try:
            os.replace(temporary, target)
            record.file_size = replacement.size
            record.save(update_fields=["file_size"])
        except Exception:
            if target.exists():
                target.unlink()
            os.replace(backup, target)
            raise
        backup.unlink(missing_ok=True)
    except OSError:
        temporary.unlink(missing_ok=True)
        if backup.exists() and not target.exists():
            os.replace(backup, target)
        return JsonResponse({"error": "替换失败，请检查磁盘空间或文件占用情况。"}, status=500)
    except Exception:
        temporary.unlink(missing_ok=True)
        return JsonResponse({"error": "记录更新失败，已恢复原文件。"}, status=500)
    return JsonResponse({"message": "文件内容已替换。", "size": replacement.size})


@csrf_exempt
@require_POST
def delete_file(request, upload_id):
    if not allowed_client(request):
        return JsonResponse({"error": "请先连接已授权设备。"}, status=403)
    record = UploadRecord.objects.filter(id=upload_id).first()
    if not record:
        return JsonResponse({"error": "文件记录不存在。"}, status=404)
    target = settings.UPLOAD_DIR / record.stored_name
    try:
        if target.exists():
            target.unlink()
        record.delete()
    except OSError:
        return JsonResponse({"error": "删除失败，请检查文件是否正被其他程序占用。"}, status=500)
    return JsonResponse({"message": "文件和记录已删除。"})


def device_status(request):
    if not is_local_admin(request):
        return HttpResponseForbidden("仅可在电脑本机管理连接设备。")
    now = timezone.now()
    devices = []
    for device in Device.objects.filter(is_active=True):
        online = bool(device.last_seen and (now - device.last_seen).total_seconds() <= 25)
        devices.append({
            "id": device.id,
            "name": device.name,
            "online": online,
            "lastSeen": timezone.localtime(device.last_seen).isoformat(timespec="seconds") if device.last_seen else None,
        })
    return JsonResponse({
        "devices": devices,
        "onlineCount": sum(1 for item in devices if item["online"]),
        "addresses": network_addresses(),
        "activeAddress": current_host(),
    })


@csrf_exempt
@require_POST
def pair_device(request):
    if not authorized(request):
        return JsonResponse({"error": "二维码已失效，请重新扫描。"}, status=403)
    try:
        data = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({"error": "请求格式不正确。"}, status=400)
    device_key = secrets.token_urlsafe(32)
    name = re.sub(r"[\x00-\x1f<>]", "", str(data.get("name", "手机")))[:40] or "手机"
    device = Device.objects.create(
        name=name,
        key_hash=hashlib.sha256(device_key.encode("utf-8")).hexdigest(),
        last_seen=timezone.now(),
    )
    return JsonResponse({"deviceKey": device_key, "deviceId": device.id, "name": device.name})


@csrf_exempt
@require_POST
def heartbeat(request):
    device = device_for(request, update=True)
    if not device:
        return JsonResponse({"error": "设备连接已失效，请重新扫描电脑上的二维码。"}, status=403)
    return JsonResponse({"connected": True, "name": device.name})


@csrf_exempt
@require_POST
def revoke_device(request, device_id):
    if not is_local_admin(request):
        return HttpResponseForbidden("仅可在电脑本机管理已连接设备。")
    Device.objects.filter(id=device_id, is_active=True).update(is_active=False)
    return JsonResponse({"message": "设备已断开。"})


def clean_filename(value):
    value = urllib.parse.unquote(value).replace("\\", "/").split("/")[-1]
    value = "".join(char for char in value if ord(char) >= 32 and char not in '<>:"|?*')
    return value.strip(" .")[:180] or "未命名文件"


@csrf_exempt
@require_POST
def upload(request):
    if not allowed_client(request):
        return JsonResponse({"error": "请先扫描电脑上的二维码连接此设备。"}, status=403)
    try:
        content_length = int(request.META.get("CONTENT_LENGTH", "0"))
    except ValueError:
        content_length = 0
    if content_length > settings.MAX_UPLOAD_BYTES:
        return JsonResponse({"error": "单次上传不能超过 250 MB，请分批上传。"}, status=413)
    uploads = request.FILES.getlist("files")
    if not uploads:
        return JsonResponse({"error": "没有选中文件，请重新选择。"}, status=400)
    if len(uploads) > settings.MAX_FILES_PER_REQUEST:
        return JsonResponse({"error": "一次最多上传 40 个文件。"}, status=400)
    if sum(item.size for item in uploads) > settings.MAX_UPLOAD_BYTES:
        return JsonResponse({"error": "单次上传不能超过 250 MB，请分批上传。"}, status=413)
    settings.UPLOAD_DIR.mkdir(exist_ok=True)
    upload_device = device_for(request, update=True)
    saved_paths, saved = [], []
    try:
        for item in uploads:
            original_name = clean_filename(item.name)
            stored_name = "{}_{}__{}".format(
                timezone.now().strftime("%Y%m%d_%H%M%S"), secrets.token_hex(3), original_name
            )
            target = settings.UPLOAD_DIR / stored_name
            with target.open("wb") as destination:
                for chunk in item.chunks():
                    destination.write(chunk)
            saved_paths.append(target)
            UploadRecord.objects.create(
                original_name=original_name, stored_name=stored_name, file_size=item.size
            )
            if upload_device:
                TransferRecord.objects.create(
                    direction=TransferRecord.PHONE_TO_PC,
                    status=TransferRecord.COMPLETED,
                    file_name=original_name,
                    file_size=item.size,
                    transferred_size=item.size,
                    device=upload_device,
                    device_name=upload_device.name,
                )
            saved.append({"name": original_name, "size": item.size})
    except OSError:
        for path in saved_paths:
            path.unlink(missing_ok=True)
        return JsonResponse({"error": "电脑保存文件失败，请检查磁盘空间和目录权限。"}, status=500)
    return JsonResponse({"files": saved, "message": "已接收 {} 个文件".format(len(saved))}, status=201)


def file_access_allowed(request):
    if is_local_admin(request):
        return True
    return device_for(request) is not None


def get_record(request, stored_name):
    if not file_access_allowed(request):
        return None
    if Path(stored_name).name != stored_name:
        raise Http404
    return UploadRecord.objects.filter(stored_name=stored_name).first()


def download(request, stored_name):
    record = get_record(request, stored_name)
    if not record:
        if not file_access_allowed(request):
            return HttpResponseForbidden("请先连接已授权设备。")
        raise Http404
    target = settings.UPLOAD_DIR / record.stored_name
    if not target.is_file():
        raise Http404
    content_type = mimetypes.guess_type(record.original_name)[0] or "application/octet-stream"
    device = device_for(request, update=True)
    if device:
        transfer = TransferRecord.objects.create(
            direction=TransferRecord.PC_TO_PHONE,
            status=TransferRecord.TRANSFERRING,
            file_name=record.original_name,
            file_size=record.file_size,
            device=device,
            device_name=device.name,
        )

        def stream_file():
            transferred = 0
            last_saved = 0
            completed = False
            try:
                with target.open("rb") as source:
                    while True:
                        chunk = source.read(64 * 1024)
                        if not chunk:
                            break
                        yield chunk
                        transferred += len(chunk)
                        if transferred - last_saved >= 1024 * 1024:
                            TransferRecord.objects.filter(pk=transfer.pk).update(transferred_size=transferred)
                            last_saved = transferred
                completed = True
            finally:
                TransferRecord.objects.filter(pk=transfer.pk).update(
                    transferred_size=transferred,
                    status=TransferRecord.COMPLETED if completed else TransferRecord.INTERRUPTED,
                )

        response = StreamingHttpResponse(stream_file(), content_type=content_type)
        response["Content-Length"] = str(record.file_size)
    else:
        response = FileResponse(target.open("rb"), content_type=content_type)
    response["Content-Disposition"] = "attachment; filename*=UTF-8''" + urllib.parse.quote(record.original_name)
    response["X-Content-Type-Options"] = "nosniff"
    return response


def preview(request, stored_name):
    record = get_record(request, stored_name)
    if not record:
        if not file_access_allowed(request):
            return HttpResponseForbidden("请先连接已授权设备。")
        raise Http404
    extension = Path(record.original_name).suffix.lower()
    if extension not in PREVIEW_EXTENSIONS:
        raise Http404
    target = settings.UPLOAD_DIR / record.stored_name
    if not target.is_file():
        raise Http404
    if extension == ".docx":
        try:
            with zipfile.ZipFile(target) as archive:
                if archive.getinfo("word/document.xml").file_size > 20 * 1024 * 1024:
                    return HttpResponse("文档内容较大，请下载后用 Word 打开。", status=413, content_type="text/plain; charset=utf-8")
                root = ET.fromstring(archive.read("word/document.xml"))
        except (OSError, KeyError, zipfile.BadZipFile, ET.ParseError):
            return HttpResponse("Word 文件无法预览，请下载后打开。", status=422, content_type="text/plain; charset=utf-8")
        namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        body = root.find(".//" + namespace + "body")
        blocks = []
        if body is not None:
            for item in list(body):
                if item.tag == namespace + "p":
                    text = "".join(node.text or "" for node in item.iter(namespace + "t"))
                    style = item.find(namespace + "pPr/" + namespace + "pStyle")
                    style_name = style.get(namespace + "val", "") if style is not None else ""
                    heading_match = re.match(r"Heading([1-6])$", style_name)
                    if heading_match:
                        blocks.append("<h{}>{}</h{}>".format(heading_match.group(1), escape(text), heading_match.group(1)))
                    elif text.strip():
                        blocks.append("<p>{}</p>".format(escape(text)))
                elif item.tag == namespace + "tbl":
                    rows = []
                    for row in item.findall(namespace + "tr"):
                        cells = []
                        for cell in row.findall(namespace + "tc"):
                            cell_text = " ".join(
                                "".join(node.text or "" for node in para.iter(namespace + "t"))
                                for para in cell.findall(namespace + "p")
                            )
                            cells.append("<td>{}</td>".format(escape(cell_text)))
                        rows.append("<tr>{}</tr>".format("".join(cells)))
                    if rows:
                        blocks.append("<table>{}</table>".format("".join(rows)))
        document = (
            "<!doctype html><html lang='zh-CN'><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<style>body{font:16px/1.85 'Microsoft YaHei UI',sans-serif;color:#26352d;"
            "max-width:820px;margin:24px auto;padding:0 22px}h1,h2,h3{line-height:1.4}"
            "table{border-collapse:collapse;width:100%;margin:16px 0}td{border:1px solid #ccd5cd;padding:7px 10px}</style>"
            "<body>{}</body></html>"
        ).format("".join(blocks) or "<p>文档中没有可预览的文字内容。</p>")
        return HttpResponse(document, content_type="text/html; charset=utf-8")
    if extension in TEXT_EXTENSIONS:
        if target.stat().st_size > 10 * 1024 * 1024:
            return HttpResponse("文本文件较大，请下载后查看。", status=413, content_type="text/plain; charset=utf-8")
        text = target.read_bytes().decode("utf-8-sig", errors="replace")
        document = (
            "<!doctype html><html lang='zh-CN'><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<style>body{font:14px/1.75 Consolas,'Microsoft YaHei UI',monospace;color:#26352d;"
            "white-space:pre-wrap;overflow-wrap:anywhere;margin:22px}</style><body>{}</body></html>"
        ).format(escape(text))
        return HttpResponse(document, content_type="text/html; charset=utf-8")
    content_type = mimetypes.guess_type(record.original_name)[0] or "application/octet-stream"
    response = FileResponse(target.open("rb"), content_type=content_type)
    response["Content-Disposition"] = "inline"
    response["X-Content-Type-Options"] = "nosniff"
    return response
