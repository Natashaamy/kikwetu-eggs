"""UTC storage and Nairobi calendar boundaries (legacy naive timestamps are UTC)."""
from datetime import date, datetime, time, timedelta, timezone

UTC = timezone.utc
# Nairobi has no daylight saving time; fixed EAT also works without OS tzdata.
NAIROBI = timezone(timedelta(hours=3), "Africa/Nairobi")


def utc_now():
    return datetime.now(UTC)


def parse_timestamp(value):
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def business_date(value):
    return parse_timestamp(value).astimezone(NAIROBI).date()


def period_dates(period="month", start=None, end=None, today=None):
    today = today or utc_now().astimezone(NAIROBI).date()
    if period == "week":
        start = today - timedelta(days=today.weekday())
        return start, start + timedelta(days=6)
    if period == "month":
        start = today.replace(day=1)
        return start, (start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    if period != "custom" or not start or not end:
        raise ValueError("Select a week, month, or complete custom date range")
    start, end = date.fromisoformat(start), date.fromisoformat(end)
    if start > end:
        raise ValueError("Start date must not be after end date")
    return start, end


def utc_bounds(start, end):
    return (datetime.combine(start, time.min, NAIROBI).astimezone(UTC),
            datetime.combine(end + timedelta(days=1), time.min, NAIROBI).astimezone(UTC))
