from django.contrib import admin

from .models import FormResponse, Group, Profile, RegistrationForm


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ("name",)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("full_name", "user", "role", "status", "group", "phone")
    list_filter = ("role", "status", "group")


@admin.register(RegistrationForm)
class RegistrationFormAdmin(admin.ModelAdmin):
    list_display = ("title", "created_by", "is_open", "closes_on", "created_at")


@admin.register(FormResponse)
class FormResponseAdmin(admin.ModelAdmin):
    list_display = ("form", "user", "submitted_at")
