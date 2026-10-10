from django.contrib import admin

from .models import Group, Profile


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ("name",)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("full_name", "user", "role", "status", "group", "phone")
    list_filter = ("role", "status", "group")
