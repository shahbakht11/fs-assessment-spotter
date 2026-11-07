"""Settings for the weather-aware truck routing API. Stateless: no database is used."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIST = BASE_DIR.parent / "frontend" / "dist"

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-not-secret")
DEBUG = os.environ.get("DJANGO_DEBUG", "0" if os.environ.get("VERCEL") else "1") == "1"
ALLOWED_HOSTS = [h for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",") if h]
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

INSTALLED_APPS = ["planner"]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.gzip.GZipMiddleware",
]
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
DATABASES = {}
USE_TZ = True
TIME_ZONE = "UTC"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
TEMPLATES = []

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "OPTIONS": {"MAX_ENTRIES": 20_000},
    }
}

# Third-party services (all free, no API keys)
VALHALLA_URL = os.environ.get("VALHALLA_URL", "https://valhalla1.openstreetmap.de/route")
OSRM_URL = os.environ.get("OSRM_URL", "https://router.project-osrm.org/route/v1/driving")
OPEN_METEO_API_KEY = os.environ.get("OPEN_METEO_API_KEY", "")
OPEN_METEO_URL = os.environ.get(
    "OPEN_METEO_URL",
    "https://customer-api.open-meteo.com/v1/forecast" if OPEN_METEO_API_KEY else "https://api.open-meteo.com/v1/forecast",
)
# Forecast locations one plan may request; plan + heatmap must stay under the free tier's 600/min.
PLAN_LOCATION_BUDGET = int(os.environ.get("PLAN_LOCATION_BUDGET", "350"))
PHOTON_URL = os.environ.get("PHOTON_URL", "https://photon.komoot.io/api/")
NOMINATIM_URL = os.environ.get("NOMINATIM_URL", "https://nominatim.openstreetmap.org/search")
HTTP_USER_AGENT = os.environ.get("HTTP_USER_AGENT", "weather-aware-truck-routing/1.0 (assessment demo)")
HTTP_TIMEOUT_S = float(os.environ.get("HTTP_TIMEOUT_S", "20"))
WEATHER_CACHE_S = 30 * 60

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
