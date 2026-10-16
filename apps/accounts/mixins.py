from urllib.parse import urlencode

from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect


class OrgRequiredMixin(LoginRequiredMixin):
    """
    Requires login AND an attached organization.
    If not logged in, redirects to the admin login with a `next` back to here.
    If logged in but no organization, sends to dashboard root with a message.
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            # Preserve the target URL so Django returns here after login
            login_url = f"/admin/login/?{urlencode({'next': request.path})}"
            return redirect(login_url)

        if not request.user.organization_id:
            # Logged in but no org — send to a help page (or dashboard root)
            return redirect("/admin/")

        return super().dispatch(request, *args, **kwargs)


class ManagerRequiredMixin(OrgRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        if response is None and request.user.role not in ("owner", "manager"):
            return redirect("/dashboard/")
        return response