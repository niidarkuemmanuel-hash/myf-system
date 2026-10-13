import csv
import datetime
import math

from django.db import IntegrityError
from django.http import HttpResponse
from django.utils import timezone
from django.utils.crypto import get_random_string
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import FormResponse, Profile, RegistrationForm
from .views import STAFF_ROLES, is_approved, is_staff_member

QUESTION_TYPES = ("text", "textarea", "number", "date", "choice", "multi")
ID_CHARS = "abcdefghjkmnpqrstuvwxyz23456789"


def err(message, code=status.HTTP_400_BAD_REQUEST):
    return Response({"error": message}, status=code)


def get_form(form_id):
    try:
        return RegistrationForm.objects.select_related("created_by").get(id=form_id)
    except RegistrationForm.DoesNotExist:
        return None


def person_name(user):
    if user is not None and hasattr(user, "profile"):
        return user.profile.full_name
    return ""


def owns_form(user, form):
    return form.created_by_id == user.id and is_staff_member(user)


def can_edit_form(user, form):
    if not is_staff_member(user):
        return False
    return form.created_by_id == user.id or form.editors.filter(id=user.id).exists()


def form_is_open(form):
    if not form.is_open:
        return False
    if form.closes_on and form.closes_on < timezone.localdate():
        return False
    return True


def safe_cell(value):
    text = "" if value is None else str(value)
    if text[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text


def clean_questions(raw):
    if not isinstance(raw, list):
        raise ValueError("The questions could not be read.")
    if len(raw) > 30:
        raise ValueError("A form can have at most 30 questions.")
    cleaned = []
    used = set()
    for q in raw:
        if not isinstance(q, dict):
            raise ValueError("The questions could not be read.")
        label = str(q.get("label", "")).strip()
        if not label:
            raise ValueError("Every question needs some text.")
        if len(label) > 200:
            raise ValueError("A question is too long (200 characters at most).")
        qtype = q.get("type")
        if qtype not in QUESTION_TYPES:
            raise ValueError("Unknown question type.")
        qid = str(q.get("id") or "")
        if not qid or qid in used or len(qid) > 20 or not qid.isalnum():
            qid = "q" + get_random_string(6, ID_CHARS)
        used.add(qid)
        item = {
            "id": qid,
            "label": label,
            "type": qtype,
            "required": bool(q.get("required")),
        }
        if qtype in ("choice", "multi"):
            options = []
            for o in q.get("options") or []:
                text = str(o).strip()[:100]
                if text and text not in options:
                    options.append(text)
            if len(options) < 2:
                raise ValueError('"' + label + '" needs at least 2 options.')
            if len(options) > 20:
                raise ValueError('"' + label + '" can have at most 20 options.')
            item["options"] = options
        cleaned.append(item)
    return cleaned


def clean_answers(questions, raw):
    if not isinstance(raw, dict):
        raise ValueError("Your answers could not be read.")
    out = {}
    for q in questions:
        label = q["label"]
        qtype = q["type"]
        val = raw.get(q["id"])
        if isinstance(val, str):
            val = val.strip()
        if val is None or val == "" or val == []:
            if q.get("required"):
                raise ValueError("Please answer: " + label)
            continue
        if qtype in ("text", "textarea"):
            val = str(val)
            if len(val) > (300 if qtype == "text" else 2000):
                raise ValueError('Your answer to "' + label + '" is too long.')
        elif qtype == "number":
            try:
                number = float(str(val))
            except ValueError:
                raise ValueError('"' + label + '" must be a number.')
            if not math.isfinite(number):
                raise ValueError('"' + label + '" must be a number.')
            val = str(val)[:30]
        elif qtype == "date":
            try:
                datetime.date.fromisoformat(str(val))
            except ValueError:
                raise ValueError('"' + label + '" must be a valid date.')
            val = str(val)
        elif qtype == "choice":
            if val not in q.get("options", []):
                raise ValueError('Please pick one of the options for "' + label + '".')
        elif qtype == "multi":
            if not isinstance(val, list):
                raise ValueError('Please pick from the options for "' + label + '".')
            chosen = []
            for v in val:
                if v not in q.get("options", []):
                    raise ValueError('Please pick from the options for "' + label + '".')
                if v not in chosen:
                    chosen.append(v)
            val = chosen
        out[q["id"]] = val
    return out


def apply_form_fields(form, data, creating=False):
    if creating or "title" in data:
        title = str(data.get("title", "")).strip()
        if not title:
            raise ValueError("Please give the form a title.")
        if len(title) > 200:
            raise ValueError("The title is too long.")
        form.title = title
    if "description" in data:
        form.description = str(data.get("description") or "").strip()[:2000]
    if "is_open" in data:
        form.is_open = bool(data.get("is_open"))
    if "closes_on" in data:
        raw = data.get("closes_on")
        if raw in (None, ""):
            form.closes_on = None
        else:
            try:
                form.closes_on = datetime.date.fromisoformat(str(raw))
            except ValueError:
                raise ValueError("That closing date is not valid.")
    if "questions" in data:
        form.questions = clean_questions(data.get("questions"))


def form_data(form, user, detail=False):
    owner = owns_form(user, form)
    can_edit = can_edit_form(user, form)
    mine = form.responses.filter(user=user).first()
    data = {
        "id": form.id,
        "title": form.title,
        "description": form.description,
        "is_open": form.is_open,
        "closes_on": form.closes_on.isoformat() if form.closes_on else None,
        "open_now": form_is_open(form),
        "created_by": person_name(form.created_by),
        "created_at": form.created_at,
        "is_owner": owner,
        "can_edit": can_edit,
        "submitted": mine is not None,
    }
    if can_edit:
        data["response_count"] = form.responses.count()
    if detail:
        data["questions"] = form.questions
        data["my_answers"] = mine.answers if mine else None
        data["my_submitted_at"] = mine.submitted_at if mine else None
        if owner:
            data["editors"] = [
                {"id": e.profile.id, "full_name": e.profile.full_name}
                for e in form.editors.select_related("profile")
            ]
            data["candidates"] = [
                {"id": p.id, "full_name": p.full_name, "role": p.role}
                for p in Profile.objects.filter(
                    status="approved", role__in=STAFF_ROLES
                )
                .exclude(user=user)
                .order_by("full_name")
            ]
    return data


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def forms_collection(request):
    if not is_approved(request.user):
        return err("Your account is not approved yet.", status.HTTP_403_FORBIDDEN)
    if request.method == "GET":
        items = RegistrationForm.objects.select_related("created_by").order_by("-created_at")
        return Response([form_data(f, request.user) for f in items])

    if not is_staff_member(request.user):
        return err("Only the chairman, secretary or treasurer can create forms.", status.HTTP_403_FORBIDDEN)
    form = RegistrationForm(created_by=request.user)
    try:
        apply_form_fields(form, request.data, creating=True)
    except ValueError as e:
        return err(str(e))
    form.save()
    return Response(
        form_data(form, request.user, detail=True), status=status.HTTP_201_CREATED
    )


@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def form_detail(request, form_id):
    if not is_approved(request.user):
        return err("Your account is not approved yet.", status.HTTP_403_FORBIDDEN)
    form = get_form(form_id)
    if form is None:
        return err("Not found.", status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        return Response(form_data(form, request.user, detail=True))

    if request.method == "DELETE":
        if not owns_form(request.user, form):
            return err(
                "Only the person who created this form can delete it.",
                status.HTTP_403_FORBIDDEN,
            )
        form.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    if not can_edit_form(request.user, form):
        return err(
            "You do not have permission to edit this form.", status.HTTP_403_FORBIDDEN
        )
    try:
        apply_form_fields(form, request.data)
    except ValueError as e:
        return err(str(e))
    form.save()
    return Response(form_data(form, request.user, detail=True))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def form_submit(request, form_id):
    if not is_approved(request.user):
        return err("Your account is not approved yet.", status.HTTP_403_FORBIDDEN)
    form = get_form(form_id)
    if form is None:
        return err("Not found.", status.HTTP_404_NOT_FOUND)
    if not form_is_open(form):
        return err("Registration for this form is closed.")
    if form.responses.filter(user=request.user).exists():
        return err("You have already registered.")
    try:
        answers = clean_answers(form.questions, request.data.get("answers", {}))
    except ValueError as e:
        return err(str(e))
    try:
        FormResponse.objects.create(form=form, user=request.user, answers=answers)
    except IntegrityError:
        return err("You have already registered.")
    return Response(
        form_data(form, request.user, detail=True), status=status.HTTP_201_CREATED
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def form_responses(request, form_id):
    form = get_form(form_id)
    if form is None:
        return err("Not found.", status.HTTP_404_NOT_FOUND)
    if not can_edit_form(request.user, form):
        return err(
            "You do not have permission to see these registrations.",
            status.HTTP_403_FORBIDDEN,
        )
    rows = []
    for r in form.responses.select_related("user__profile__group").order_by("submitted_at"):
        prof = r.user.profile
        rows.append(
            {
                "id": r.id,
                "full_name": prof.full_name,
                "phone": prof.phone,
                "level": prof.level,
                "school": prof.school,
                "group": prof.group.name if prof.group else "",
                "submitted_at": r.submitted_at,
                "answers": r.answers,
            }
        )
    return Response({"questions": form.questions, "responses": rows})


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def form_response_detail(request, form_id, response_id):
    form = get_form(form_id)
    if form is None:
        return err("Not found.", status.HTTP_404_NOT_FOUND)
    if not can_edit_form(request.user, form):
        return err(
            "You do not have permission to remove registrations.",
            status.HTTP_403_FORBIDDEN,
        )
    deleted, _ = form.responses.filter(id=response_id).delete()
    if not deleted:
        return err("Not found.", status.HTTP_404_NOT_FOUND)
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def form_editors(request, form_id):
    form = get_form(form_id)
    if form is None:
        return err("Not found.", status.HTTP_404_NOT_FOUND)
    if not owns_form(request.user, form):
        return err(
            "Only the person who created this form can share it.",
            status.HTTP_403_FORBIDDEN,
        )
    raw = request.data.get("editors", [])
    if not isinstance(raw, list):
        return err("The list of people could not be read.")
    try:
        ids = [int(i) for i in raw]
    except (ValueError, TypeError):
        return err("The list of people could not be read.")
    profiles = (
        Profile.objects.filter(id__in=ids, status="approved", role__in=STAFF_ROLES)
        .exclude(user=request.user)
        .select_related("user")
    )
    form.editors.set([p.user for p in profiles])
    return Response(form_data(form, request.user, detail=True))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def form_export(request, form_id):
    form = get_form(form_id)
    if form is None:
        return err("Not found.", status.HTTP_404_NOT_FOUND)
    if not can_edit_form(request.user, form):
        return err(
            "You do not have permission to see these registrations.",
            status.HTTP_403_FORBIDDEN,
        )
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="registrations-%d.csv"' % form.id
    response.write("\ufeff")
    writer = csv.writer(response)
    questions = form.questions
    writer.writerow(
        ["Name", "Phone", "Level", "School", "Group", "Registered on"]
        + [safe_cell(q["label"]) for q in questions]
    )
    for r in form.responses.select_related("user__profile__group").order_by("submitted_at"):
        prof = r.user.profile
        row = [
            prof.full_name,
            prof.phone,
            prof.level,
            prof.school,
            prof.group.name if prof.group else "",
            r.submitted_at.strftime("%Y-%m-%d %H:%M"),
        ]
        for q in questions:
            v = r.answers.get(q["id"], "")
            row.append(", ".join(v) if isinstance(v, list) else v)
        writer.writerow([safe_cell(x) for x in row])
    return response
