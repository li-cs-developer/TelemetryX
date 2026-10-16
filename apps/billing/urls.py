from django.urls import path
from .views import BillingHome, ChangePlanView

urlpatterns = [
    path("", BillingHome.as_view(), name="billing-home"),
    path("change-plan/", ChangePlanView.as_view(), name="billing-change-plan"),
]