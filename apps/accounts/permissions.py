from rest_framework import permissions


class HasOrganization(permissions.BasePermission):
    message = "You must belong to an organization."

    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated
            and request.user.organization_id
        )


class IsManager(permissions.BasePermission):
    message = "Manager or owner role required."

    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated
            and request.user.organization_id
            and request.user.role in ("owner", "manager")
        )


class IsOwner(permissions.BasePermission):
    message = "Owner role required."

    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated
            and request.user.role == "owner"
        )