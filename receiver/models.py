from django.db import models


class UploadRecord(models.Model):
    original_name = models.CharField(max_length=180)
    stored_name = models.CharField(max_length=230, unique=True)
    file_size = models.PositiveBigIntegerField()
    uploaded_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-uploaded_at"]
        verbose_name = "接收文件"
        verbose_name_plural = "接收文件"

    def __str__(self):
        return self.original_name


class Device(models.Model):
    name = models.CharField(max_length=40)
    key_hash = models.CharField(max_length=64, unique=True)
    is_active = models.BooleanField(default=True)
    paired_at = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-last_seen", "-paired_at"]

    def __str__(self):
        return self.name


class TransferRecord(models.Model):
    PHONE_TO_PC = "phone_to_pc"
    PC_TO_PHONE = "pc_to_phone"
    DIRECTION_CHOICES = [
        (PHONE_TO_PC, "手机到电脑"),
        (PC_TO_PHONE, "电脑到手机"),
    ]
    TRANSFERRING = "transferring"
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"
    STATUS_CHOICES = [
        (TRANSFERRING, "传输中"),
        (COMPLETED, "已完成"),
        (INTERRUPTED, "已中断"),
    ]

    direction = models.CharField(max_length=16, choices=DIRECTION_CHOICES)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=TRANSFERRING)
    file_name = models.CharField(max_length=180)
    file_size = models.PositiveBigIntegerField()
    transferred_size = models.PositiveBigIntegerField(default=0)
    device = models.ForeignKey(Device, null=True, blank=True, on_delete=models.SET_NULL, related_name="transfers")
    device_name = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return "{} · {}".format(self.get_direction_display(), self.file_name)
