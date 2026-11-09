from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("receiver", "0003_remove_securityconfig")]

    operations = [
        migrations.CreateModel(
            name="TransferRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("direction", models.CharField(choices=[("phone_to_pc", "手机到电脑"), ("pc_to_phone", "电脑到手机")], max_length=16)),
                ("status", models.CharField(choices=[("transferring", "传输中"), ("completed", "已完成"), ("interrupted", "已中断")], default="transferring", max_length=16)),
                ("file_name", models.CharField(max_length=180)),
                ("file_size", models.PositiveBigIntegerField()),
                ("transferred_size", models.PositiveBigIntegerField(default=0)),
                ("device_name", models.CharField(blank=True, max_length=40)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("device", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="transfers", to="receiver.device")),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
