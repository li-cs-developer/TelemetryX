"""
Billing stub. No Stripe. We just:
 - assign a default plan when an org is created
 - enforce vehicle cap on vehicle creation
 - enforce ingestion cap (vehicles × pings/sec) in the throttle
"""
from .models import Plan, Subscription


def get_or_create_subscription(org) -> Subscription:
    sub = getattr(org, "subscription", None)
    if sub:
        return sub

    default = Plan.objects.filter(is_default=True).first() or Plan.objects.first()
    if default is None:
        # Belt and braces: bootstrap a plan if none exist
        default = Plan.objects.create(
            code="trial", name="Trial", max_vehicles=3,
            max_pings_per_second=5, monthly_price_cents=0, is_default=True,
        )
    return Subscription.objects.create(organization=org, plan=default, status="trialing")


def can_add_vehicle(org) -> tuple[bool, str]:
    sub = get_or_create_subscription(org)
    if not sub.is_writable():
        return False, f"Subscription is {sub.status}; upgrade or reactivate to add vehicles."
    if not sub.has_capacity_for_new_vehicle():
        return False, (
            f"Plan '{sub.plan.code}' allows {sub.plan.max_vehicles} vans. "
            f"Upgrade to add more."
        )
    return True, ""


def change_plan(org, plan_code: str) -> Subscription:
    sub = get_or_create_subscription(org)
    plan = Plan.objects.get(code=plan_code)
    sub.plan = plan
    sub.status = "active"
    sub.save(update_fields=["plan", "status"])
    return sub