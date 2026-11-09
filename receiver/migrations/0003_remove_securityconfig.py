from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("receiver", "0002_securityconfig_device")]
    operations = [
        migrations.DeleteModel(name="SecurityConfig"),
    ]
