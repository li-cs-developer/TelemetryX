from django.contrib import admin
from .models import SafetyEvent, AlertEmail


@admin.register(SafetyEvent)
class SafetyEventAdmin(admin.ModelAdmin):
    list_display = ("driver", "vehicle", "kind", "value", "occurred_at")
    list_filter = ("kind",)


@admin.register(AlertEmail)
class AlertEmailAdmin(admin.ModelAdmin):
    list_display = ("recipient", "subject", "status", "related_kind", "created_at")
    list_filter = ("status", "related_kind")
    readonly_fields = ("created_at", "sent_at")
    search_fields = ("recipient", "subject")