from django.contrib.auth import authenticate
from django.utils.crypto import get_random_string
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import Announcement, AttendanceRecord, Group, Profile, SiteSettings
from .serializers import (
    AnnouncementSerializer,
    AttendanceSerializer,
    ProfileFullSerializer,
    ProfileNameSerializer,
    SignupSerializer,
)

STAFF_ROLES = ("executive", "treasurer")


def is_approved(user):
    profile = getattr(user, "profile", None)
    return bool(profile and profile.status == "approved")


def is_staff_member(user):
    return is_approved(user) and user.profile.role in STAFF_ROLES


# ---------- Sign up, login, my account ----------

@api_view(["POST"])
@permission_classes([AllowAny])
def signup(request):
    """Anyone can sign up. They wait as 'pending' until an executive approves."""
    serializer = SignupSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(
        {"message": "Sign-up received. An executive will approve your account."},
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def login(request):
    user = authenticate(
        username=request.data.get("username"),
        password=request.data.get("password"),
    )
    if user is None:
        return Response(
            {"error": "Wrong username or password."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not is_approved(user):
        return Response(
            {"error": "Your account is still waiting for approval."},
            status=status.HTTP_403_FORBIDDEN,
        )
    token, _ = Token.objects.get_or_create(user=user)
    return Response(
        {"token": token.key, "profile": ProfileFullSerializer(user.profile).data}
    )


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def me(request):
    profile = request.user.profile
    if request.method == "PATCH":
        limits = {"full_name": 150, "phone": 20, "level": 100, "school": 150}
        for field, limit in limits.items():
            if field in request.data:
                value = str(request.data[field]).strip()[:limit]
                if field in ("full_name", "phone") and not value:
                    return Response(
                        {"error": "Name and phone number cannot be empty."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                setattr(profile, field, value)
        if "group" in request.data:
            gid = request.data.get("group")
            if gid in (None, "", 0):
                profile.group = None
            else:
                try:
                    profile.group = Group.objects.get(id=gid)
                except (Group.DoesNotExist, ValueError, TypeError):
                    return Response(
                        {"error": "That group does not exist."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
        profile.save()
    return Response(ProfileFullSerializer(profile).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def change_password(request):
    old = request.data.get("old_password", "")
    new = request.data.get("new_password", "")
    if not request.user.check_password(old):
        return Response(
            {"error": "Your current password is wrong."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if len(new) < 6:
        return Response(
            {"error": "The new password must have at least 6 characters."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    request.user.set_password(new)
    request.user.save()
    return Response({"message": "Password changed."})


# ---------- Members ----------

@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def members(request):
    if not is_approved(request.user):
        return Response(
            {"error": "Your account is not approved yet."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if request.method == "GET":
        approved = (
            Profile.objects.filter(status="approved")
            .select_related("group")
            .order_by("full_name")
        )
        if is_staff_member(request.user):
            return Response(ProfileFullSerializer(approved, many=True).data)
        # Regular members see names only
        return Response(ProfileNameSerializer(approved, many=True).data)

    # POST: an executive registers a member directly (already approved)
    if not is_staff_member(request.user):
        return Response(
            {"error": "Only executives can register members."},
            status=status.HTTP_403_FORBIDDEN,
        )
    serializer = SignupSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    profile = serializer.save()
    profile.status = "approved"
    profile.save()
    return Response(
        ProfileFullSerializer(profile).data, status=status.HTTP_201_CREATED
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def set_member_group(request, profile_id):
    if not is_staff_member(request.user):
        return Response(
            {"error": "Only executives can change a person's group."},
            status=status.HTTP_403_FORBIDDEN,
        )
    try:
        profile = Profile.objects.get(id=profile_id)
    except Profile.DoesNotExist:
        return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
    gid = request.data.get("group")
    if gid in (None, "", 0):
        profile.group = None
    else:
        try:
            profile.group = Group.objects.get(id=gid)
        except (Group.DoesNotExist, ValueError, TypeError):
            return Response(
                {"error": "That group does not exist."},
                status=status.HTTP_400_BAD_REQUEST,
            )
    profile.save()
    return Response(ProfileFullSerializer(profile).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def pending(request):
    if not is_staff_member(request.user):
        return Response(
            {"error": "Only executives can see pending sign-ups."},
            status=status.HTTP_403_FORBIDDEN,
        )
    waiting = (
        Profile.objects.filter(status="pending")
        .select_related("group")
        .order_by("full_name")
    )
    return Response(ProfileFullSerializer(waiting, many=True).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def approve(request, profile_id):
    if not is_staff_member(request.user):
        return Response(
            {"error": "Only executives can approve sign-ups."},
            status=status.HTTP_403_FORBIDDEN,
        )
    try:
        profile = Profile.objects.get(id=profile_id)
    except Profile.DoesNotExist:
        return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
    profile.status = "approved"
    profile.save()
    return Response(ProfileFullSerializer(profile).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def reset_password(request, profile_id):
    if not is_staff_member(request.user):
        return Response(
            {"error": "Only executives can reset passwords."},
            status=status.HTTP_403_FORBIDDEN,
        )
    try:
        target = Profile.objects.select_related("user").get(id=profile_id)
    except Profile.DoesNotExist:
        return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    if target.user_id == request.user.id:
        return Response(
            {"error": "Use My account to change your own password."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    allowed = target.role == "member" or (
        request.user.profile.role == "treasurer" and target.role == "executive"
    )
    if not allowed:
        return Response(
            {"error": "You cannot reset this person's password."},
            status=status.HTTP_403_FORBIDDEN,
        )

    temp = get_random_string(8, "abcdefghjkmnpqrstuvwxyz23456789")
    target.user.set_password(temp)
    target.user.save()
    Token.objects.filter(user=target.user).delete()
    return Response(
        {
            "temporary_password": temp,
            "username": target.user.username,
            "full_name": target.full_name,
        }
    )


# ---------- Groups ----------

@api_view(["GET", "POST"])
@permission_classes([AllowAny])
def groups(request):
    """Anyone can read the group list (the sign-up form needs it). Only executives can add."""
    if request.method == "GET":
        return Response([{"id": g.id, "name": g.name} for g in Group.objects.all()])

    if not (request.user.is_authenticated and is_staff_member(request.user)):
        return Response(
            {"error": "Only executives can add groups."},
            status=status.HTTP_403_FORBIDDEN,
        )
    name = str(request.data.get("name", "")).strip()
    if not name:
        return Response(
            {"error": "Please enter a group name."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if len(name) > 80:
        return Response(
            {"error": "The group name is too long."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if Group.objects.filter(name__iexact=name).exists():
        return Response(
            {"error": "That group already exists."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    group = Group.objects.create(name=name)
    return Response(
        {"id": group.id, "name": group.name}, status=status.HTTP_201_CREATED
    )


@api_view(["PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def group_detail(request, group_id):
    if not is_staff_member(request.user):
        return Response(
            {"error": "Only executives can change groups."},
            status=status.HTTP_403_FORBIDDEN,
        )
    try:
        group = Group.objects.get(id=group_id)
    except Group.DoesNotExist:
        return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "DELETE":
        group.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    name = str(request.data.get("name", "")).strip()
    if not name:
        return Response(
            {"error": "Please enter a group name."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if len(name) > 80:
        return Response(
            {"error": "The group name is too long."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if Group.objects.filter(name__iexact=name).exclude(id=group.id).exists():
        return Response(
            {"error": "That group already exists."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    group.name = name
    group.save()
    return Response({"id": group.id, "name": group.name})


# ---------- Announcements ----------

@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def announcements(request):
    if not is_approved(request.user):
        return Response(
            {"error": "Your account is not approved yet."},
            status=status.HTTP_403_FORBIDDEN,
        )
    if request.method == "GET":
        items = Announcement.objects.all()
        return Response(
            AnnouncementSerializer(items, many=True, context={"request": request}).data
        )

    if not is_staff_member(request.user):
        return Response(
            {"error": "Only executives can post announcements."},
            status=status.HTTP_403_FORBIDDEN,
        )
    serializer = AnnouncementSerializer(data=request.data, context={"request": request})
    serializer.is_valid(raise_exception=True)
    upload = request.FILES.get("media")
    media_type = ""
    if upload:
        media_type = "video" if upload.content_type.startswith("video/") else "image"
    serializer.save(created_by=request.user, media_type=media_type)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def announcement_detail(request, announcement_id):
    if not is_staff_member(request.user):
        return Response(
            {"error": "Only executives can delete announcements."},
            status=status.HTTP_403_FORBIDDEN,
        )
    try:
        item = Announcement.objects.get(id=announcement_id)
    except Announcement.DoesNotExist:
        return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
    if item.media:
        item.media.delete(save=False)
    item.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


# ---------- Attendance ----------

@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def attendance(request):
    if not is_staff_member(request.user):
        return Response(
            {"error": "Only executives can see or take attendance."},
            status=status.HTTP_403_FORBIDDEN,
        )
    if request.method == "GET":
        records = AttendanceRecord.objects.all()
        return Response(AttendanceSerializer(records, many=True).data)

    serializer = AttendanceSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    serializer.save(recorded_by=request.user)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_attendance(request):
    if not is_approved(request.user):
        return Response(
            {"error": "Your account is not approved yet."},
            status=status.HTTP_403_FORBIDDEN,
        )
    profile = request.user.profile
    records = AttendanceRecord.objects.all()
    rows = [
        {
            "event": r.event,
            "date": r.date,
            "present": r.present.filter(id=profile.id).exists(),
        }
        for r in records
    ]
    return Response(
        {
            "attended": sum(1 for row in rows if row["present"]),
            "total_meetings": len(rows),
            "records": rows,
        }
    )


# ---------- Site settings ----------

def _site_data(site, request):
    url = ""
    if site.login_background:
        url = request.build_absolute_uri(site.login_background.url)
    return {
        "login_background": url,
        "updated_at": site.updated_at,
        "short_name": site.short_name,
        "motto": site.motto,
        "intro_text": site.intro_text,
    }


@api_view(["GET", "POST", "PATCH", "DELETE"])
@permission_classes([AllowAny])
def site_settings(request):
    """Anyone can read the site settings. Only executives can change them."""
    site = SiteSettings.get()
    if request.method == "GET":
        return Response(_site_data(site, request))

    if not (request.user.is_authenticated and is_staff_member(request.user)):
        return Response(
            {"error": "Only executives can change the site settings."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if request.method == "PATCH":
        short = str(request.data.get("short_name", site.short_name)).strip()
        motto = str(request.data.get("motto", site.motto))
        intro = str(request.data.get("intro_text", site.intro_text)).strip()
        if not short:
            return Response(
                {"error": "The short name cannot be empty."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        lines = [line.strip() for line in motto.splitlines() if line.strip()]
        if len(lines) > 3:
            return Response(
                {"error": "The motto can have at most 3 lines."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        site.short_name = short[:60]
        site.motto = "\n".join(lines)[:200]
        site.intro_text = intro[:300]
        site.save()
        return Response(_site_data(site, request))

    if request.method == "POST":
        upload = request.FILES.get("image")
        if not upload:
            return Response(
                {"error": "Please choose a picture."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not (upload.content_type or "").startswith("image/"):
            return Response(
                {"error": "Only pictures are allowed."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if upload.size > 5 * 1024 * 1024:
            return Response(
                {"error": "That picture is bigger than 5 MB. Please choose a smaller one."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if site.login_background:
            site.login_background.delete(save=False)
        site.login_background = upload
        site.save()
        return Response(_site_data(site, request))

    if site.login_background:
        site.login_background.delete(save=False)
        site.login_background = None
        site.save()
    return Response(_site_data(site, request))
