from django.contrib.auth.models import AbstractUser
from django.db import models


class Organization(models.Model):
    name = models.CharField(max_length=150)
    slug = models.SlugField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class User(AbstractUser):
    ROLE_CHOICES = [
        ("owner", "Owner"),
        ("manager", "Manager"),
        ("viewer", "Viewer"),
    ]
    organization = models.ForeignKey(
        Organization, null=True, blank=True,
        on_delete=models.CASCADE, related_name="users",
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="viewer")

    @property
    def is_manager(self):
        return self.role in ("owner", "manager")

    @property
    def is_owner(self):
        return self.role == "owner"

    def __str__(self):
        return self.username