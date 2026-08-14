from datetime import UTC, datetime
from zoneinfo import ZoneInfo, available_timezones

JST = ZoneInfo("Asia/Tokyo")
YAHOO_DATETIME_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M")


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


def to_user_tz(dt: datetime, tz_name: str) -> datetime:
    return dt.astimezone(ZoneInfo(tz_name))


def format_user_time(dt: datetime, tz_name: str) -> str:
    return to_user_tz(dt, tz_name).strftime("%H:%M")


def format_price(value: int | None) -> str:
    if value is None:
        return "—"
    return f"¥{value:,}"
