import csv
import datetime
from decimal import Decimal, InvalidOperation

from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import DuesItem, DuesPayment, Profile
from .views import is_approved

METHODS = ("cash", "momo", "bank", "other", "waived")
ZERO = Decimal("0.00")
MAX_AMOUNT = Decimal("99999999.99")
MAX_MONTHS = 120
ADVANCE_MONTHS = 12
DENIED = "Only the Treasurer can use the dues pages."


def err(message, code=status.HTTP_400_BAD_REQUEST):
    return Response({"error": message}, status=code)


def is_treasurer(user):
    return is_approved(user) and user.profile.role == "treasurer"


def money_value(raw):
    try:
        value = Decimal(str(raw).strip())
        if not value.is_finite():
            raise InvalidOperation
        value = value.quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise ValueError("Please enter a valid amount.")
    if value <= ZERO:
        raise ValueError("The amount must be more than zero.")
    if value > MAX_AMOUNT:
        raise ValueError("That amount is too large.")
    return value


def parse_date(raw):
    if raw in (None, ""):
        return None
    try:
        return datetime.date.fromisoformat(str(raw))
    except ValueError:
        raise ValueError("That date is not valid.")


def parse_month(raw):
    """Accepts 'YYYY-MM' or a full date and returns the first day of that month."""
    if raw in (None, ""):
        return None
    text = str(raw).strip()
    try:
        if len(text) == 7:
            text = text + "-01"
        return datetime.date.fromisoformat(text).replace(day=1)
    except ValueError:
        raise ValueError("That month is not valid.")


def current_month():
    return timezone.localdate().replace(day=1)


def month_index(d):
    return d.year * 12 + d.month - 1


def month_from_index(i):
    return datetime.date(i // 12, i % 12 + 1, 1)


def month_key(d):
    return d.strftime("%Y-%m")


def safe_cell(value):
    text = "" if value is None else str(value)
    if text[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text


def get_item(item_id):
    try:
        return DuesItem.objects.get(id=item_id)
    except DuesItem.DoesNotExist:
        return None


def member_start(item, member_id):
    raw = (item.member_starts or {}).get(str(member_id))
    if raw:
        try:
            return parse_month(raw)
        except ValueError:
            pass
    return item.start_month or current_month()


def months_due(item, start):
    last = current_month()
    if item.end_month and item.end_month < last:
        last = item.end_month
    n = month_index(last) - month_index(start) + 1
    return max(0, min(n, MAX_MONTHS))


def payable_total(item, start):
    """The most that can be recorded for one person."""
    if not item.monthly:
        return item.amount
    if item.end_month:
        total = month_index(item.end_month) - month_index(start) + 1
    else:
        total = months_due(item, start) + ADVANCE_MONTHS
    return item.amount * max(0, min(total, MAX_MONTHS))


def month_chips(item, start, due, covered):
    full = int(covered // item.amount)
    rest = covered - item.amount * full
    last = min(max(due, full + (1 if rest > ZERO else 0)), MAX_MONTHS)
    base = month_index(start)
    chips = []
    for i in range(last):
        if i < full:
            state = "paid"
        elif i == full and rest > ZERO:
            state = "partial"
        else:
            state = "unpaid"
        chips.append(
            {
                "month": month_key(month_from_index(base + i)),
                "status": state,
                "future": i >= due,
            }
        )
    return chips


def item_rows(item):
    by_member = {}
    for p in item.payments.all():
        by_member.setdefault(p.member_id, []).append(p)
    rows = []
    for m in item.members.select_related("group").order_by("full_name"):
        plist = by_member.get(m.id, [])
        paid = sum((p.amount for p in plist if p.method != "waived"), ZERO)
        waived = sum((p.amount for p in plist if p.method == "waived"), ZERO)
        covered = paid + waived
        if item.monthly:
            start = member_start(item, m.id)
            due = months_due(item, start)
            charge = item.amount * due
        else:
            start = None
            due = None
            charge = item.amount
        balance = max(charge - covered, ZERO)
        ahead = max(covered - charge, ZERO)
        if item.monthly and charge == ZERO and covered == ZERO:
            state = "upcoming"
        elif balance <= ZERO:
            state = "waived" if paid == ZERO and waived > ZERO else "paid"
        elif covered > ZERO:
            state = "partial"
        else:
            state = "unpaid"
        row = {
            "member_id": m.id,
            "full_name": m.full_name,
            "group_name": m.group.name if m.group else "",
            "phone": m.phone,
            "charge": str(charge),
            "paid": str(paid),
            "waived": str(waived),
            "balance": str(balance),
            "ahead": str(ahead),
            "status": state,
            "payments": [
                {
                    "id": p.id,
                    "amount": str(p.amount),
                    "method": p.method,
                    "paid_on": p.paid_on.isoformat(),
                    "note": p.note,
                }
                for p in plist
            ],
        }
        if item.monthly:
            full = int(covered // item.amount)
            row["start"] = month_key(start)
            row["months_due"] = due
            row["months_behind"] = max(due - full, 0)
            row["paid_through"] = (
                month_key(month_from_index(month_index(start) + full - 1))
                if full > 0
                else ""
            )
            row["months"] = month_chips(item, start, due, covered)
        rows.append(row)
    return rows


def item_data(item, detail=False):
    rows = item_rows(item)
    collected = sum((Decimal(r["paid"]) for r in rows), ZERO)
    waived = sum((Decimal(r["waived"]) for r in rows), ZERO)
    outstanding = sum((Decimal(r["balance"]) for r in rows), ZERO)
    expected = sum((Decimal(r["charge"]) for r in rows), ZERO)
    data = {
        "id": item.id,
        "name": item.name,
        "amount": str(item.amount),
        "monthly": item.monthly,
        "due_date": item.due_date.isoformat() if item.due_date else None,
        "start_month": month_key(item.start_month) if item.start_month else None,
        "end_month": month_key(item.end_month) if item.end_month else None,
        "people": len(rows),
        "expected": str(expected),
        "collected": str(collected),
        "waived": str(waived),
        "outstanding": str(outstanding),
        "cleared": sum(1 for r in rows if r["status"] in ("paid", "waived", "upcoming")),
    }
    if detail:
        data["rows"] = rows
        data["member_ids"] = [r["member_id"] for r in rows]
        data["everyone"] = [
            {
                "id": p.id,
                "full_name": p.full_name,
                "group_name": p.group.name if p.group else "",
            }
            for p in Profile.objects.filter(status="approved")
            .select_related("group")
            .order_by("full_name")
        ]
    return data


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def dues_collection(request):
    if not is_treasurer(request.user):
        return err(DENIED, status.HTTP_403_FORBIDDEN)
    if request.method == "GET":
        return Response([item_data(i) for i in DuesItem.objects.all()])

    data = request.data
    name = str(data.get("name", "")).strip()
    if not name:
        return err("Please enter a name for these dues.")
    if len(name) > 120:
        return err("The name is too long.")
    monthly = bool(data.get("monthly"))
    try:
        amount = money_value(data.get("amount"))
        if monthly:
            start_month = parse_month(data.get("start_month"))
            if start_month is None:
                raise ValueError("Choose the month the dues start.")
            end_month = parse_month(data.get("end_month"))
            if end_month and end_month < start_month:
                raise ValueError("The last month cannot be before the first month.")
            due_date = None
        else:
            due_date = parse_date(data.get("due_date"))
            start_month = None
            end_month = None
    except ValueError as e:
        return err(str(e))

    raw = data.get("members", "all")
    approved = Profile.objects.filter(status="approved")
    if raw == "all":
        people = list(approved)
    else:
        try:
            ids = [int(i) for i in raw]
        except (TypeError, ValueError):
            return err("The list of people could not be read.")
        people = list(approved.filter(id__in=ids))
    if not people:
        return err("Choose at least one person.")

    item = DuesItem.objects.create(
        name=name,
        amount=amount,
        monthly=monthly,
        due_date=due_date,
        start_month=start_month,
        end_month=end_month,
    )
    item.members.set(people)
    return Response(item_data(item, detail=True), status=status.HTTP_201_CREATED)


@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def dues_detail(request, item_id):
    if not is_treasurer(request.user):
        return err(DENIED, status.HTTP_403_FORBIDDEN)
    item = get_item(item_id)
    if item is None:
        return err("Not found.", status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        return Response(item_data(item, detail=True))

    if request.method == "DELETE":
        item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    data = request.data
    try:
        if "name" in data:
            name = str(data.get("name", "")).strip()
            if not name:
                raise ValueError("Please enter a name for these dues.")
            if len(name) > 120:
                raise ValueError("The name is too long.")
            item.name = name
        if "amount" in data:
            item.amount = money_value(data.get("amount"))
        if item.monthly:
            if "start_month" in data:
                start = parse_month(data.get("start_month"))
                if start is None:
                    raise ValueError("Choose the month the dues start.")
                item.start_month = start
            if "end_month" in data:
                item.end_month = parse_month(data.get("end_month"))
            if item.end_month and item.start_month and item.end_month < item.start_month:
                raise ValueError("The last month cannot be before the first month.")
        elif "due_date" in data:
            item.due_date = parse_date(data.get("due_date"))
    except ValueError as e:
        return err(str(e))
    item.save()
    return Response(item_data(item, detail=True))


@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def dues_members(request, item_id):
    if not is_treasurer(request.user):
        return err(DENIED, status.HTTP_403_FORBIDDEN)
    item = get_item(item_id)
    if item is None:
        return err("Not found.", status.HTTP_404_NOT_FOUND)
    raw = request.data.get("members", [])
    try:
        ids = [int(i) for i in raw]
    except (TypeError, ValueError):
        return err("The list of people could not be read.")
    new = set(
        Profile.objects.filter(id__in=ids, status="approved").values_list("id", flat=True)
    )
    if not new:
        return err("Choose at least one person.")
    current = set(item.members.values_list("id", flat=True))
    blocked = set(
        item.payments.filter(member_id__in=current - new).values_list(
            "member__full_name", flat=True
        )
    )
    if blocked:
        return err(
            "These people have payments recorded, so they cannot be removed yet: "
            + ", ".join(sorted(blocked))
            + ". Remove their payments first."
        )
    starts = dict(item.member_starts or {})
    if item.monthly:
        try:
            new_start = parse_month(request.data.get("new_start")) or current_month()
        except ValueError as e:
            return err(str(e))
        for pid in new - current:
            starts[str(pid)] = month_key(new_start)
    for pid in current - new:
        starts.pop(str(pid), None)
    item.member_starts = starts
    item.save()
    item.members.set(new)
    return Response(item_data(item, detail=True))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def dues_payments(request, item_id):
    if not is_treasurer(request.user):
        return err(DENIED, status.HTTP_403_FORBIDDEN)
    item = get_item(item_id)
    if item is None:
        return err("Not found.", status.HTTP_404_NOT_FOUND)
    data = request.data
    try:
        member_id = int(data.get("member"))
    except (TypeError, ValueError):
        return err("Choose a person.")
    member = item.members.filter(id=member_id).first()
    if member is None:
        return err("That person does not owe these dues.")
    try:
        amount = money_value(data.get("amount"))
        paid_on = parse_date(data.get("paid_on")) or timezone.localdate()
    except ValueError as e:
        return err(str(e))
    method = data.get("method", "cash")
    if method not in METHODS:
        return err("Choose how it was paid.")
    note = str(data.get("note", "")).strip()[:200]

    row = next((r for r in item_rows(item) if r["member_id"] == member.id), None)
    covered = (Decimal(row["paid"]) + Decimal(row["waived"])) if row else ZERO
    start = member_start(item, member.id) if item.monthly else None
    limit = payable_total(item, start) - covered
    if amount > limit:
        return err(
            "That is more than can be recorded for this person. The most is "
            + str(max(limit, ZERO))
            + "."
        )

    DuesPayment.objects.create(
        item=item,
        member=member,
        amount=amount,
        method=method,
        paid_on=paid_on,
        note=note,
        recorded_by=request.user,
    )
    return Response(item_data(item, detail=True), status=status.HTTP_201_CREATED)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def dues_payment_detail(request, item_id, payment_id):
    if not is_treasurer(request.user):
        return err(DENIED, status.HTTP_403_FORBIDDEN)
    item = get_item(item_id)
    if item is None:
        return err("Not found.", status.HTTP_404_NOT_FOUND)
    deleted, _ = item.payments.filter(id=payment_id).delete()
    if not deleted:
        return err("Not found.", status.HTTP_404_NOT_FOUND)
    return Response(item_data(item, detail=True))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dues_export(request, item_id):
    if not is_treasurer(request.user):
        return err(DENIED, status.HTTP_403_FORBIDDEN)
    item = get_item(item_id)
    if item is None:
        return err("Not found.", status.HTTP_404_NOT_FOUND)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="dues-%d.csv"' % item.id
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow(
        [
            "Name", "Group", "Phone", "Owed so far", "Paid", "Waived",
            "Balance", "Paid through", "Months behind", "Status",
        ]
    )
    for r in item_rows(item):
        writer.writerow(
            [
                safe_cell(r["full_name"]),
                safe_cell(r["group_name"]),
                safe_cell(r["phone"]),
                r["charge"],
                r["paid"],
                r["waived"],
                r["balance"],
                r.get("paid_through", ""),
                r.get("months_behind", ""),
                r["status"],
            ]
        )
    return response


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_dues(request):
    """Every approved person can see their OWN dues, and only their own."""
    if not is_approved(request.user):
        return err("Your account is not approved yet.", status.HTTP_403_FORBIDDEN)
    profile = request.user.profile
    items = []
    total_paid = ZERO
    total_balance = ZERO
    for item in DuesItem.objects.filter(members=profile):
        row = next((r for r in item_rows(item) if r["member_id"] == profile.id), None)
        if row is None:
            continue
        total_paid += Decimal(row["paid"])
        total_balance += Decimal(row["balance"])
        entry = {
            "id": item.id,
            "name": item.name,
            "amount": str(item.amount),
            "monthly": item.monthly,
            "due_date": item.due_date.isoformat() if item.due_date else None,
            "paid": row["paid"],
            "waived": row["waived"],
            "balance": row["balance"],
            "ahead": row["ahead"],
            "status": row["status"],
            "payments": [
                {"amount": p["amount"], "method": p["method"], "paid_on": p["paid_on"]}
                for p in row["payments"]
            ],
        }
        if item.monthly:
            entry.update(
                {
                    "start_month": row["start"],
                    "months_due": row["months_due"],
                    "months_behind": row["months_behind"],
                    "paid_through": row["paid_through"],
                    "months": row["months"],
                }
            )
        items.append(entry)
    return Response(
        {
            "items": items,
            "total_paid": str(total_paid),
            "total_balance": str(total_balance),
        }
    )
