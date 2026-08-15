import re
from datetime import UTC, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, available_timezones

JST = ZoneInfo("Asia/Tokyo")
YAHOO_DATETIME_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M")

UTC_OFFSET_RE = re.compile(
    r"^UTC\s*(?P<sign>[+-])\s*(?P<hours>\d{1,2})(?::(?P<minutes>\d{1,2}))?$",
    re.IGNORECASE,
)
MIN_UTC_OFFSET_MINUTES = -12 * 60
MAX_UTC_OFFSET_MINUTES = 14 * 60
ALLOWED_OFFSET_MINUTES = {0, 15, 30, 45}

OFFSET_LABELS = {
    3: "Москва",
    2: "Берлин",
    1: "Париж",
    0: "Лондон",
    9: "Токио",
    8: "Пекин",
}


class YahooDatetimeParseError(ValueError):
    pass


def ensure_aware(dt: datetime | None) -> datetime | None:
    """Гарантирует aware-datetime (UTC) — БД может вернуть naive значения."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def parse_yahoo_datetime(value: str, tz: ZoneInfo = JST) -> datetime:
    """Парсит наивное JST-время Yahoo и возвращает aware datetime в UTC."""
    value = value.strip()
    for fmt in YAHOO_DATETIME_FORMATS:
        try:
            naive = datetime.strptime(value, fmt)
        except ValueError:
            continue
        return naive.replace(tzinfo=tz).astimezone(UTC)
    raise YahooDatetimeParseError(f"Unparseable Yahoo datetime: {value!r}")


def is_valid_timezone(tz_name: str) -> bool:
    return tz_name in available_timezones()


def normalize_utc_offset(value: str) -> str | None:
    """Приводит ввод вида 'UTC+3'/'utc -5:30' к каноническому 'UTC+3'.

    Возвращает None, если значение не является корректным смещением UTC.
    """
    match = UTC_OFFSET_RE.match(value.strip())
    if not match:
        return None
    sign = 1 if match.group("sign") == "+" else -1
    hours = int(match.group("hours"))
    minutes = int(match.group("minutes") or 0)
    if hours > 14 or minutes > 59 or minutes not in ALLOWED_OFFSET_MINUTES:
        return None
    total = sign * (hours * 60 + minutes)
    if not MIN_UTC_OFFSET_MINUTES <= total <= MAX_UTC_OFFSET_MINUTES:
        return None
    if minutes:
        return f"UTC{'+' if sign > 0 else '-'}{hours}:{minutes:02d}"
    return f"UTC{'+' if sign > 0 else '-'}{hours}"


def get_zone(tz_name: str) -> timezone | ZoneInfo:
    """Возвращает tzinfo для сохранённого значения: 'UTC+n' или IANA-имени."""
    offset = normalize_utc_offset(tz_name)
    if offset is not None:
        sign = 1 if offset[3] == "+" else -1
        hours, _, minutes = offset[4:].partition(":")
        delta = timedelta(
            minutes=sign * (int(hours) * 60 + (int(minutes) if minutes else 0))
        )
        return timezone(delta)
    if tz_name in available_timezones():
        return ZoneInfo(tz_name)
    return UTC


def format_timezone(tz_name: str) -> str:
    """Отображает часовой пояс пользователя в формате 'UTC+n (Москва)'."""
    offset = normalize_utc_offset(tz_name)
    if offset is None:
        zone = get_zone(tz_name)
        now = datetime.now(UTC)
        delta = now.astimezone(zone).utcoffset() or timedelta(0)
        total_minutes = int(delta.total_seconds() // 60)
        sign = "+" if total_minutes >= 0 else "-"
        abs_minutes = abs(total_minutes)
        hours, minutes = divmod(abs_minutes, 60)
        if minutes:
            offset = f"UTC{sign}{hours}:{minutes:02d}"
        else:
            offset = f"UTC{sign}{hours}"
    label = None
    if ":" not in offset:
        signed_hours = int(offset[3:])
        label = OFFSET_LABELS.get(signed_hours)
    if label:
        return f"{offset} ({label})"
    return offset


def to_user_tz(dt: datetime, tz_name: str) -> datetime:
    return dt.astimezone(get_zone(tz_name))


def format_user_time(dt: datetime, tz_name: str) -> str:
    return to_user_tz(dt, tz_name).strftime("%H:%M")


def format_price(value: int | None) -> str:
    if value is None:
        return "—"
    return f"¥{value:,}"
