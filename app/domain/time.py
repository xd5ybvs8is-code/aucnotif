from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

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


def format_remaining(end_time: datetime, now: datetime | None = None) -> str:
    """Относительное время до окончания аукциона в компактном виде.

    Возвращает '2 дн 3 ч', '1 ч 25 мин', '45 мин', 'меньше минуты'
    или 'завершён' для прошедшего end_time.
    """
    if now is None:
        now = datetime.now(UTC)
    delta = end_time - now
    if delta < timedelta(0):
        return "завершён"
    total = int(delta.total_seconds())
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return f"{days} дн {hours} ч"
    if hours:
        return f"{hours} ч {minutes} мин" if minutes else f"{hours} ч"
    if minutes:
        return f"{minutes} мин"
    return "меньше минуты"


def format_price(value: int | None) -> str:
    if value is None:
        return "—"
    return f"¥{value:,}"
