from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from app.domain.time import (
    YahooDatetimeParseError,
    format_price,
    format_user_time,
    is_valid_timezone,
    parse_yahoo_datetime,
)


def test_parse_yahoo_datetime_jst_to_utc():
    parsed = parse_yahoo_datetime("2026-08-13 22:40:31")
    assert parsed == datetime(2026, 8, 13, 13, 40, 31, tzinfo=UTC)


def test_parse_yahoo_datetime_with_whitespace():
    parsed = parse_yahoo_datetime("  2026-08-13 22:40:31  ")
    assert parsed == datetime(2026, 8, 13, 13, 40, 31, tzinfo=UTC)


def test_parse_yahoo_datetime_invalid_raises():
    with pytest.raises(YahooDatetimeParseError):
        parse_yahoo_datetime("not-a-date")


def test_parse_yahoo_datetime_empty_raises():
    with pytest.raises(YahooDatetimeParseError):
        parse_yahoo_datetime("")


def test_user_timezone_conversion():
    dt = datetime(2026, 8, 13, 13, 40, 31, tzinfo=UTC)
    london = ZoneInfo("Europe/London")
    tokyo = ZoneInfo("Asia/Tokyo")
    assert format_user_time(dt, "Europe/London") == dt.astimezone(london).strftime("%H:%M")
    assert format_user_time(dt, "Asia/Tokyo") == dt.astimezone(tokyo).strftime("%H:%M")


def test_format_price():
    assert format_price(24000) == "¥24,000"
    assert format_price(0) == "¥0"
    assert format_price(None) == "—"


def test_is_valid_timezone():
    assert is_valid_timezone("Europe/Moscow") is True
    assert is_valid_timezone("Asia/Tokyo") is True
    assert is_valid_timezone("Not/AZone") is False
    assert is_valid_timezone("") is False


def test_naive_datetime_never_returned():
    parsed = parse_yahoo_datetime("2026-08-13 22:40:31")
    assert parsed.tzinfo is not None
