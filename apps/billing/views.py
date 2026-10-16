from django.shortcuts import redirect
from django.contrib import messages
from django.views.generic import TemplateView

from apps.accounts.mixins import OrgRequiredMixin, ManagerRequiredMixin
from .models import Plan
from .services import get_or_create_subscription, change_plan


class BillingHome(OrgRequiredMixin, TemplateView):
    template_name = "billing/billing.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = self.request.user.organization
        sub = get_or_create_subscription(org)
        ctx["subscription"] = sub
        ctx["plans"] = Plan.objects.all()
        ctx["vehicle_count"] = sub.vehicle_count()
        ctx["can_change_plan"] = self.request.user.is_manager
        return ctx


class ChangePlanView(ManagerRequiredMixin, TemplateView):
    """
    Stub action: switches plan without payment. Guarded to manager+ role.
    """
    def post(self, request, *args, **kwargs):
        plan_code = request.POST.get("plan_code", "").strip()
        org = request.user.organization
        try:
            change_plan(org, plan_code)
            messages.success(request, f"Switched to plan '{plan_code}'.")
        except Plan.DoesNotExist:
            messages.error(request, f"Unknown plan '{plan_code}'.")
        return redirect("billing-home")