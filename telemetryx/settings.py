from pathlib import Path
import os
import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
environ.Env.read_env(os.path.join(BASE_DIR, ".env"))

SECRET_KEY = env("SECRET_KEY", default="dev-only")
DEBUG = env.bool("DEBUG", default=True)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["*"])

INSTALLED_APPS = [
    "whitenoise.runserver_nostatic",
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "channels",
    "apps.accounts",
    "apps.fleet",
    "apps.billing",
    "apps.telemetry",
    "apps.alerts",
    "apps.dashboard",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

ROOT_URLCONF = "telemetryx.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "telemetryx.wsgi.application"
ASGI_APPLICATION = "telemetryx.asgi.application"

DATABASES = {"default": env.db("DATABASE_URL")}

AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "/admin/login/"

# ---------------------------------------------------------------------------
# AWS / DynamoDB
# ---------------------------------------------------------------------------
# With DYNAMODB_ENDPOINT set to http://localhost:8000, boto3 talks to your
# local DynamoDB Local instance instead of real AWS. Leave it EMPTY (or unset)
# in production to hit real AWS — boto3 will read ~/.aws/credentials or IAM.
AWS_REGION = env("AWS_REGION", default="us-east-1")
DYNAMODB_ENDPOINT = env("DYNAMODB_ENDPOINT", default=None) or None
DYNAMODB_TABLE = env("DYNAMODB_TABLE", default="TelemetryXTelemetry")

AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID", default="fakeMyKeyId")
AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY", default="fakeSecretAccessKey")

# ---------------------------------------------------------------------------
# Celery
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://localhost:6379/1")
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=False)
CELERY_BEAT_SCHEDULE = {
    "nightly-driver-rollup": {
        "task": "apps.telemetry.aggregation.rollup_yesterday",
        "schedule": 60 * 60 * 24,
    },
    "flush-ping-buffer": {
        "task": "apps.telemetry.batcher.flush_ping_buffer",
        # 100ms cadence — Celery beat's minimum granularity is ~1s in practice,
        # so this runs each second and drains whatever is queued.
        "schedule": 1.0,
    },
}

# ---------------------------------------------------------------------------
# Channels
# ---------------------------------------------------------------------------
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [env("CHANNEL_LAYERS_REDIS", default="redis://localhost:6379/2")],
        },
    },
}

# ---------------------------------------------------------------------------
# DRF
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_THROTTLE_RATES": {
        "per_vin": "1/second",
        "per_ip": "20/second",
    },
}

# ---------------------------------------------------------------------------
# Batch ingestion
# ---------------------------------------------------------------------------
BATCH_INGESTION_ENABLED = env.bool("BATCH_INGESTION_ENABLED", default=False)
BATCH_QUEUE_KEY = "telemetryx:ping_buffer"
BATCH_SIZE = 25
BATCH_FLUSH_INTERVAL_MS = 100
BATCH_MAX_QUEUE = 10000   # if queue grows beyond this, drop oldest and warn

# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
HEALTHCHECK_TOKEN = env("HEALTHCHECK_TOKEN", default="")

BILLING_STUB = True