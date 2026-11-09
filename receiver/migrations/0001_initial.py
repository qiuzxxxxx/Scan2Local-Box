from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="UploadRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("original_name", models.CharField(max_length=180)),
                ("stored_name", models.CharField(max_length=230, unique=True)),
                ("file_size", models.PositiveBigIntegerField()),
                ("uploaded_at", models.DateTimeField(db_index=True, auto_now_add=True)),
            ],
            options={
                "ordering": ["-uploaded_at"],
                "verbose_name": "接收文件",
                "verbose_name_plural": "接收文件",
            },
        ),
    ]
