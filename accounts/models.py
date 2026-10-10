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
    group = models.ForeignKey(
        "Group", on_delete=models.SET_NULL, null=True, blank=True, related_name="members"
    )
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


class Group(models.Model):
    name = models.CharField(max_length=80, unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "fellowship group"
        verbose_name_plural = "fellowship groups"

    def __str__(self):
        return self.name


class Announcement(models.Model):
    title = models.CharField(max_length=200)
    message = models.TextField(blank=True)
    media = models.FileField(upload_to="announcements/", blank=True, null=True)
    media_type = models.CharField(max_length=10, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class AttendanceRecord(models.Model):
    event = models.CharField(max_length=200)
    date = models.DateField()
    present = models.ManyToManyField(Profile, blank=True, related_name="attended")
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return f"{self.event} ({self.date})"


class SiteSettings(models.Model):
    login_background = models.FileField(upload_to="site/", blank=True, null=True)
    short_name = models.CharField(max_length=60, default="Rev. Ebmmc MYF")
    motto = models.TextField(default="We work.\nWe witness.\nWe worship.")
    intro_text = models.TextField(
        default="Rev. Ebmmc MYF. Log in to see notices, your attendance and who is in the fellowship."
    )
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "Site settings"
