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