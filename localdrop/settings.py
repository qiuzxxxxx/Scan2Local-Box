from pathlib import Path
import secrets

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = secrets.token_urlsafe(48)
DEBUG = False
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = ["receiver"]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
]
ROOT_URLCONF = "localdrop.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": []},
}]
WSGI_APPLICATION = "localdrop.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
FILE_UPLOAD_MAX_MEMORY_SIZE = 2_500_000
DATA_UPLOAD_MAX_MEMORY_SIZE = 250 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FILES = 50

TRANSFER_TOKEN = secrets.token_urlsafe(18)
MAX_UPLOAD_BYTES = 250 * 1024 * 1024
MAX_FILES_PER_REQUEST = 40
UPLOAD_DIR = BASE_DIR / "received"
