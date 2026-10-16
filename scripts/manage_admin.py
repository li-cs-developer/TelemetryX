"""
Admin helper for TelemetryX.

Usage (all from project root with venv active):

    python scripts/manage_admin.py list
        Show every user with role, org, staff/superuser flags.

    python scripts/manage_admin.py grant <username> <org_slug> <role>
        Assign user to an organization with a role.
        role must be one of: owner, manager, viewer

    python scripts/manage_admin.py superuser <username>
        Set is_staff=True and is_superuser=True.

    python scripts/manage_admin.py unblock <username>
        Shortcut for: grant to acme-logistics as owner + make superuser.
"""
import os
import sys
from pathlib import Path

import django

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "telemetryx.settings")
django.setup()

from apps.accounts.models import Organization, User  # noqa: E402


VALID_ROLES = {"owner", "manager", "viewer"}


def cmd_list():
    print(f"{'USERNAME':<20} {'ROLE':<10} {'ORG':<20} {'STAFF':<7} {'SUPER':<6}")
    print("-" * 65)
    for u in User.objects.order_by("username"):
        org = u.organization.slug if u.organization else "(none)"
        print(f"{u.username:<20} {u.role:<10} {org:<20} "
              f"{str(u.is_staff):<7} {str(u.is_superuser):<6}")


def cmd_grant(username, org_slug, role):
    if role not in VALID_ROLES:
        print(f"ERROR: role must be one of {sorted(VALID_ROLES)}")
        sys.exit(1)
    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        print(f"ERROR: user '{username}' not found.")
        sys.exit(1)
    try:
        org = Organization.objects.get(slug=org_slug)
    except Organization.DoesNotExist:
        print(f"ERROR: org '{org_slug}' not found. Available:")
        for o in Organization.objects.all():
            print(f"  - {o.slug}")
        sys.exit(1)

    user.organization = org
    user.role = role
    user.save(update_fields=["organization", "role"])
    print(f"OK: {username} -> org={org.slug} role={role}")


def cmd_superuser(username):
    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        print(f"ERROR: user '{username}' not found.")
        sys.exit(1)
    user.is_staff = True
    user.is_superuser = True
    user.save(update_fields=["is_staff", "is_superuser"])
    print(f"OK: {username} is now staff + superuser.")


def cmd_unblock(username):
    # Assign the first org if any exists, else create Acme
    org = Organization.objects.first()
    if org is None:
        org = Organization.objects.create(slug="acme-logistics", name="Acme Logistics")
        print(f"Created org: {org.slug}")

    user = User.objects.get(username=username)
    user.organization = org
    user.role = "owner"
    user.is_staff = True
    user.is_superuser = True
    user.save()
    print(f"OK: {username} -> org={org.slug} role=owner staff=True superuser=True")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    args = sys.argv[2:]

    if cmd == "list":
        cmd_list()
    elif cmd == "grant":
        if len(args) != 3:
            print("Usage: grant <username> <org_slug> <role>")
            sys.exit(1)
        cmd_grant(*args)
    elif cmd == "superuser":
        if len(args) != 1:
            print("Usage: superuser <username>")
            sys.exit(1)
        cmd_superuser(*args)
    elif cmd == "unblock":
        if len(args) != 1:
            print("Usage: unblock <username>")
            sys.exit(1)
        cmd_unblock(*args)
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()