from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import AboutPhoto, Group, Leader, Profile, SiteSettings
from .views import is_approved, is_staff_member

TEXT_LIMITS = (
    ("about_text", 3000),
    ("vision_text", 1500),
    ("mission_text", 1500),
    ("uniform_text", 2000),
    ("anthem_title", 120),
    ("anthem_text", 4000),
    ("meeting_info", 1000),
    ("contact_info", 1000),
)
PHOTO_SECTIONS = ("story", "uniform", "moments")
MAX_PHOTOS_PER_SECTION = 24

POSITIONS = [
    "Immediate past chairman",
    "Chairman",
    "Vice chairman",
    "Secretary",
    "Assistant secretary",
    "Treasurer",
    "Organizer",
    "Evangelical coordinator",
    "Co-opted member",
    "BOB convenor",
]
POSITION_RANK = {p.lower(): i for i, p in enumerate(POSITIONS)}
MAX_LEADERS = 40


def err(message, code=status.HTTP_400_BAD_REQUEST):
    return Response({"error": message}, status=code)


def sorted_leaders():
    return sorted(
        Leader.objects.all(),
        key=lambda l: (POSITION_RANK.get(l.position.lower(), len(POSITIONS)), l.id),
    )


def about_payload(request):
    site = SiteSettings.get()
    data = {
        "name": site.short_name,
        "motto": [line.strip() for line in site.motto.splitlines() if line.strip()],
        "groups": [
            {"name": g.name, "count": g.members.filter(status="approved").count()}
            for g in Group.objects.all()
        ],
        "positions": POSITIONS,
        "leaders": [
            {
                "id": l.id,
                "name": l.name,
                "position": l.position,
                "photo_url": request.build_absolute_uri(l.photo.url) if l.photo else "",
            }
            for l in sorted_leaders()
        ],
        "members": Profile.objects.filter(status="approved").count(),
        "photos": [
            {
                "id": p.id,
                "section": p.section,
                "url": request.build_absolute_uri(p.image.url),
                "caption": p.caption,
            }
            for p in AboutPhoto.objects.all()
        ],
        "anthem_audio_url": (
            request.build_absolute_uri(site.anthem_audio.url) if site.anthem_audio else ""
        ),
    }
    for field, _limit in TEXT_LIMITS:
        data[field] = getattr(site, field)
    return data


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def about(request):
    if not is_approved(request.user):
        return err("Your account is not approved yet.", status.HTTP_403_FORBIDDEN)
    if request.method == "PATCH":
        if not is_staff_member(request.user):
            return err("Only executives can edit the About page.", status.HTTP_403_FORBIDDEN)
        site = SiteSettings.get()
        for field, limit in TEXT_LIMITS:
            if field in request.data:
                value = str(request.data.get(field) or "").strip()[:limit]
                setattr(site, field, value)
        site.save()
    return Response(about_payload(request))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def about_photos(request):
    if not is_staff_member(request.user):
        return err("Only executives can add pictures.", status.HTTP_403_FORBIDDEN)
    section = request.data.get("section")
    if section not in PHOTO_SECTIONS:
        return err("Choose where the picture should go.")
    upload = request.FILES.get("image")
    if not upload:
        return err("Please choose a picture.")
    if not (upload.content_type or "").startswith("image/"):
        return err("Only pictures are allowed.")
    if upload.size > 8 * 1024 * 1024:
        return err("That picture is bigger than 8 MB.")
    if AboutPhoto.objects.filter(section=section).count() >= MAX_PHOTOS_PER_SECTION:
        return err("That part already has 24 pictures. Remove one first.")
    AboutPhoto.objects.create(
        section=section,
        image=upload,
        caption=str(request.data.get("caption", "")).strip()[:200],
    )
    return Response(about_payload(request), status=status.HTTP_201_CREATED)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def about_photo_detail(request, photo_id):
    if not is_staff_member(request.user):
        return err("Only executives can remove pictures.", status.HTTP_403_FORBIDDEN)
    try:
        photo = AboutPhoto.objects.get(id=photo_id)
    except AboutPhoto.DoesNotExist:
        return err("Not found.", status.HTTP_404_NOT_FOUND)
    photo.image.delete(save=False)
    photo.delete()
    return Response(about_payload(request))


@api_view(["POST", "DELETE"])
@permission_classes([IsAuthenticated])
def about_audio(request):
    if not is_staff_member(request.user):
        return err("Only executives can change the recording.", status.HTTP_403_FORBIDDEN)
    site = SiteSettings.get()
    if request.method == "DELETE":
        if site.anthem_audio:
            site.anthem_audio.delete(save=False)
            site.anthem_audio = None
            site.save()
        return Response(about_payload(request))

    upload = request.FILES.get("audio")
    if not upload:
        return err("Please choose a recording.")
    if not (upload.content_type or "").startswith("audio/"):
        return err("Only audio files are allowed (for example MP3 or M4A).")
    if upload.size > 15 * 1024 * 1024:
        return err("That recording is bigger than 15 MB.")
    if site.anthem_audio:
        site.anthem_audio.delete(save=False)
    site.anthem_audio = upload
    site.save()
    return Response(about_payload(request))


def photo_problem(upload):
    if not (upload.content_type or "").startswith("image/"):
        return "Only pictures are allowed."
    if upload.size > 6 * 1024 * 1024:
        return "That picture is bigger than 6 MB."
    return None


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def about_leaders(request):
    if not is_staff_member(request.user):
        return err("Only executives can edit the leadership.", status.HTTP_403_FORBIDDEN)
    name = str(request.data.get("name", "")).strip()
    position = str(request.data.get("position", "")).strip()
    if not name:
        return err("Please enter a name.")
    if not position:
        return err("Please choose a position.")
    if len(name) > 150 or len(position) > 80:
        return err("The name or position is too long.")
    if Leader.objects.count() >= MAX_LEADERS:
        return err("There are already 40 leaders. Remove one first.")
    upload = request.FILES.get("photo")
    if upload:
        problem = photo_problem(upload)
        if problem:
            return err(problem)
    Leader.objects.create(name=name, position=position, photo=upload)
    return Response(about_payload(request), status=status.HTTP_201_CREATED)


@api_view(["PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def about_leader_detail(request, leader_id):
    if not is_staff_member(request.user):
        return err("Only executives can edit the leadership.", status.HTTP_403_FORBIDDEN)
    try:
        leader = Leader.objects.get(id=leader_id)
    except Leader.DoesNotExist:
        return err("Not found.", status.HTTP_404_NOT_FOUND)

    if request.method == "DELETE":
        if leader.photo:
            leader.photo.delete(save=False)
        leader.delete()
        return Response(about_payload(request))

    if "name" in request.data:
        name = str(request.data.get("name", "")).strip()
        if not name or len(name) > 150:
            return err("Please enter a name (150 characters at most).")
        leader.name = name
    if "position" in request.data:
        position = str(request.data.get("position", "")).strip()
        if not position or len(position) > 80:
            return err("Please choose a position (80 characters at most).")
        leader.position = position
    upload = request.FILES.get("photo")
    if upload:
        problem = photo_problem(upload)
        if problem:
            return err(problem)
        if leader.photo:
            leader.photo.delete(save=False)
        leader.photo = upload
    elif str(request.data.get("remove_photo", "")).lower() in ("1", "true") and leader.photo:
        leader.photo.delete(save=False)
        leader.photo = None
    leader.save()
    return Response(about_payload(request))
