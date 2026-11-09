from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("receiver", "0001_initial")]
    operations = [
        migrations.CreateModel(
            name="SecurityConfig",
            fields=[
                ("key", models.CharField(default="default", max_length=20, primary_key=True, serialize=False)),
                ("code_hash", models.CharField(max_length=200)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="Device",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=40)),
                ("key_hash", models.CharField(max_length=64, unique=True)),
                ("is_active", models.BooleanField(default=True)),
                ("paired_at", models.DateTimeField(auto_now_add=True)),
                ("last_seen", models.DateTimeField(blank=True, null=True)),
            ],
            options={"ordering": ["-last_seen", "-paired_at"]},
        ),
    ]
