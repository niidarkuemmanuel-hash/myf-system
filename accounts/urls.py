from django.urls import path

from . import views

urlpatterns = [
    path("signup/", views.signup),
    path("login/", views.login),
    path("me/", views.me),
    path("members/", views.members),
    path("pending/", views.pending),
    path("approve/<int:profile_id>/", views.approve),
    path("announcements/", views.announcements),
    path("announcements/<int:announcement_id>/", views.announcement_detail),
    path("attendance/", views.attendance),
    path("my-attendance/", views.my_attendance),
]
