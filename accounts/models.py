from django.conf import settings
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


class Profile(models.Model):
    ROLES = [
        ("member", "Member"),
        ("executive", "Executive"),
        ("treasurer", "Treasurer"),
    ]
    STATUSES = [
        ("pending", "Pending approval"),
        ("approved", "Approved"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20, blank=True)
    level = models.CharField(max_length=100, blank=True)
    role = models.CharField(max_length=20, choices=ROLES, default="member")
    status = models.CharField(max_length=20, choices=STATUSES, default="pending")

    def __str__(self):
        return f"{self.full_name or self.user.username} ({self.role}, {self.status})"


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_profile(sender, instance, created, **kwargs):
    if created:
        if instance.is_superuser:
            Profile.objects.create(
                user=instance,
                full_name=instance.username,
                role="treasurer",
                status="approved",
            )
        else:
            Profile.objects.create(user=instance, full_name=instance.username)