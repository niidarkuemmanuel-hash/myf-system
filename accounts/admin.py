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


from .models import DuesItem, DuesPayment


@admin.register(DuesItem)
class DuesItemAdmin(admin.ModelAdmin):
    list_display = ("name", "amount", "due_date", "created_at")


@admin.register(DuesPayment)
class DuesPaymentAdmin(admin.ModelAdmin):
    list_display = ("item", "member", "amount", "method", "paid_on")
