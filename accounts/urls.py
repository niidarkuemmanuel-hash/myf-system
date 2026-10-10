from django.urls import path

from . import form_views, views

urlpatterns = [
    path("signup/", views.signup),
    path("login/", views.login),
    path("me/", views.me),
    path("members/", views.members),
    path("members/<int:profile_id>/group/", views.set_member_group),
    path("pending/", views.pending),
    path("approve/<int:profile_id>/", views.approve),
    path("announcements/", views.announcements),
    path("announcements/<int:announcement_id>/", views.announcement_detail),
    path("attendance/", views.attendance),
    path("my-attendance/", views.my_attendance),
    path("site/", views.site_settings),
    path("change-password/", views.change_password),
    path("reset-password/<int:profile_id>/", views.reset_password),
    path("groups/", views.groups),
    path("groups/<int:group_id>/", views.group_detail),
    path("forms/", form_views.forms_collection),
    path("forms/<int:form_id>/", form_views.form_detail),
    path("forms/<int:form_id>/submit/", form_views.form_submit),
    path("forms/<int:form_id>/responses/", form_views.form_responses),
    path("forms/<int:form_id>/responses/<int:response_id>/", form_views.form_response_detail),
    path("forms/<int:form_id>/editors/", form_views.form_editors),
    path("forms/<int:form_id>/export/", form_views.form_export),
]
