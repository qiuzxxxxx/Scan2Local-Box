# 本地收件箱：开发者文档

本文面向维护和扩展项目的开发者。普通用户请先看 [README.md](README.md)。

## 技术栈与启动

- Python 3
- Django 5.2.18（见 `requirements.txt`）
- SQLite
- 原生 HTML、CSS 和 JavaScript 前端（`index.html`）

Windows 下双击 `start.bat`：脚本检查 Django、运行 `python manage.py migrate --noinput`，然后以 `0.0.0.0:8765` 启动 Django 开发服务器。手动启动可运行：

```powershell
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 0.0.0.0:8765 --noreload
```

电脑本机管理页面使用 `http://127.0.0.1:8765/`。`start.bat` 使用 Django 开发服务器，当前配置面向可信局域网试用。

## 传输与认证流程

1. 服务启动时，`localdrop/settings.py` 生成随机 `TRANSFER_TOKEN`。电脑页面将局域网地址和此凭证组成分享地址，`receiver/qr.py` 将地址编码为 SVG 二维码。
2. 扫码设备携带二维码凭证访问网页，并向 `/api/pair` 发起配对请求。服务核验凭证后生成随机设备密钥，只将该密钥的 SHA-256 摘要存入 `Device.key_hash`；原始密钥由浏览器保存在 `localStorage`。
3. 后续请求通过 `X-Device-Key` 请求头提交设备密钥。服务计算摘要并查找有效设备。电脑本机页面则通过 loopback 地址（`127.0.0.1` 或 `::1`）识别为管理端。
4. 上传使用浏览器 `XMLHttpRequest` 和 `FormData` 向 `/api/upload` 发送 multipart HTTP 请求。Django 分块读取文件并写入 `received/`，随后将文件元数据写入 SQLite。前端使用浏览器上传进度事件展示进度。
5. 下载由 `/download/<stored_name>` 提供。设备下载会以 `StreamingHttpResponse` 分块读取，并更新传输记录；本机管理端下载使用 `FileResponse`。

文件传输直接走手机与电脑之间的局域网 HTTP 请求，没有云端中转、WebSocket 或外部存储服务。当前实现不启用 TLS；二维码凭证和设备密钥用于连接授权，不对 HTTP 流量加密。

刷新二维码会在当前服务进程内重新生成连接凭证，旧二维码不能再配对新设备；已有设备密钥不因此自动撤销。重启服务会重新生成连接凭证，但设备记录保存在数据库中，已配对设备仍可凭本地保存的有效设备密钥连接。若要撤销某设备，使用设备连接页面的“断开”操作。

## 目录与数据

- `manage.py`：Django 管理入口。
- `localdrop/settings.py`：Django、SQLite、上传目录和上传限制配置。
- `localdrop/urls.py`：URL 路由。
- `receiver/views.py`：页面、配对、上传下载、文件管理、预览及传输记录视图。
- `receiver/models.py`：`UploadRecord`、`Device`、`TransferRecord` 数据模型。
- `receiver/migrations/`：数据库迁移。
- `receiver/qr.py`：二维码矩阵与 SVG 生成。
- `index.html`：桌面和手机共用的前端页面及交互逻辑。
- `received/`：上传文件的实际存储目录；重命名、替换和删除会操作此目录中的文件。
- `db.sqlite3`：文件元数据、设备授权状态及传输记录。

## 主要接口

- `GET /`：电脑本机管理页面；带有效 `token` 参数时提供手机页面。
- `GET /qr.svg`：返回当前连接地址对应的 SVG 二维码。
- `POST /api/pair`：凭二维码凭证配对设备并返回设备密钥。
- `POST /api/heartbeat`：更新设备最近在线时间。
- `POST /api/upload`：上传文件。
- `GET /api/files`、`GET /api/transfers`：获取文件列表和传输记录。
- `GET /download/<stored_name>`、`GET /preview/<stored_name>`：下载或预览文件。
- `POST /api/files/<id>/rename`、`replace`、`delete`：管理已接收文件。
- `GET /api/devices`、`POST /api/devices/<id>/revoke`：查看及撤销设备；只允许本机管理端访问。
- `POST /api/refresh-link`：本机管理端刷新二维码凭证或选择电脑网络地址。

数据模型以 `receiver/models.py` 为准。文件名会经过清理；上传总大小上限为 250 MiB，每次最多 40 个文件（`localdrop/settings.py`）。修改模型后创建并应用迁移：

```powershell
python manage.py makemigrations receiver
python manage.py migrate
```

## 运行注意事项

- 服务器监听 `0.0.0.0:8765` 才能让局域网中的手机访问；仅在电脑本机打开页面时，使用 `127.0.0.1`。
- Windows 防火墙需要允许可信专用网络上的入站连接。手机扫码失败时，先确认当前二维码选中了手机可访问的电脑网卡地址。
- 网络切换后可在管理页面选择对应网卡并刷新二维码。若电脑开启热点，二维码地址应是手机连接该热点后可访问的电脑地址。
- 数据库和上传文件分开保存。备份或迁移时应同时处理 `db.sqlite3` 与 `received/`，并在停止服务后操作。
- 文件访问受设备密钥授权保护，但传输本身未加密。不要将服务端口暴露到不可信网络。
