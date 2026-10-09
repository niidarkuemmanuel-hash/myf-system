from django.contrib.auth import authenticate
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import Profile
from .serializers import (
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


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    return Response(ProfileFullSerializer(request.user.profile).data)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def members(request):
    if not is_approved(request.user):
        return Response(
            {"error": "Your account is not approved yet."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if request.method == "GET":
        approved = Profile.objects.filter(status="approved").order_by("full_name")
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


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def pending(request):
    if not is_staff_member(request.user):
        return Response(
            {"error": "Only executives can see pending sign-ups."},
            status=status.HTTP_403_FORBIDDEN,
        )
    waiting = Profile.objects.filter(status="pending").order_by("full_name")
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

from .models import Announcement, AttendanceRecord
from .serializers import AnnouncementSerializer, AttendanceSerializer


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
