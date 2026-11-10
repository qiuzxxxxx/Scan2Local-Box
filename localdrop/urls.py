from django.urls import path
from receiver import views

urlpatterns = [
    path("", views.home, name="home"),
    path("qr.svg", views.qr_image, name="qr_image"),
    path("api/files", views.files, name="files"),
    path("api/storage", views.storage_status, name="storage_status"),
    path("api/files/download-zip", views.download_files_zip, name="download_files_zip"),
    path("api/files/delete-batch", views.delete_files_batch, name="delete_files_batch"),
    path("api/transfers", views.transfer_history, name="transfer_history"),
    path("api/files/<int:upload_id>/rename", views.rename_file, name="rename_file"),
    path("api/files/<int:upload_id>/replace", views.replace_file, name="replace_file"),
    path("api/files/<int:upload_id>/delete", views.delete_file, name="delete_file"),
    path("api/upload", views.upload, name="upload"),
    path("api/devices", views.device_status, name="device_status"),
    path("api/refresh-link", views.refresh_link, name="refresh_link"),
    path("api/pair", views.pair_device, name="pair_device"),
    path("api/heartbeat", views.heartbeat, name="heartbeat"),
    path("api/devices/<int:device_id>/revoke", views.revoke_device, name="revoke_device"),
    path("download/<str:stored_name>", views.download, name="download"),
    path("preview/<str:stored_name>", views.preview, name="preview"),
]
