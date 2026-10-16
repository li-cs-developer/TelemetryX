from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from django.http import HttpResponse

from apps.telemetry.views import HealthCheckView


def favicon(request):
    return HttpResponse(status=204)


urlpatterns = [
    path("favicon.ico", favicon),
    path("healthz/", HealthCheckView.as_view()),
    path("", RedirectView.as_view(url="/dashboard/", permanent=False)),
    path("admin/", admin.site.urls),
    path("api/v1/", include("apps.telemetry.urls")),
    path("dashboard/billing/", include("apps.billing.urls")),
    path("dashboard/", include("apps.dashboard.urls")),
]