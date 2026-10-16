from django.contrib import admin, messages
from .models import Plan, Subscription, UsageRecord
from .services import change_plan


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "max_vehicles", "max_pings_per_second",
                    "monthly_price_cents", "is_default")


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("organization", "plan", "status", "started_at", "current_period_end")
    list_filter = ("plan", "status")
    actions = ["force_activate", "force_trial"]

    @admin.action(description="Mark selected subscriptions ACTIVE")
    def force_activate(self, request, queryset):
        queryset.update(status="active")
        self.message_user(request, "Subscriptions set to active.", messages.SUCCESS)

    @admin.action(description="Mark selected subscriptions TRIALING")
    def force_trial(self, request, queryset):
        queryset.update(status="trialing")
        self.message_user(request, "Subscriptions set to trialing.", messages.SUCCESS)


@admin.register(UsageRecord)
class UsageRecordAdmin(admin.ModelAdmin):
    list_display = ("organization", "date", "pings_ingested", "active_vehicles")
    list_filter = ("organization",)