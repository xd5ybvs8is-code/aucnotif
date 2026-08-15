from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from app.domain.time import (
    YahooDatetimeParseError,
    format_price,
    format_timezone,
    format_user_time,
    is_valid_timezone,
    normalize_utc_offset,
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


def test_normalize_utc_offset_canonical():
    assert normalize_utc_offset("UTC+3") == "UTC+3"
    assert normalize_utc_offset("UTC-5") == "UTC-5"
    assert normalize_utc_offset("UTC+0") == "UTC+0"
    assert normalize_utc_offset("UTC+5:30") == "UTC+5:30"


def test_normalize_utc_offset_case_and_spaces():
    assert normalize_utc_offset("utc+3") == "UTC+3"
    assert normalize_utc_offset("  UTC -5  ") == "UTC-5"
    assert normalize_utc_offset("UTC +3") == "UTC+3"


def test_normalize_utc_offset_invalid():
    assert normalize_utc_offset("") is None
    assert normalize_utc_offset("Europe/Moscow") is None
    assert normalize_utc_offset("UTC15") is None
    assert normalize_utc_offset("UTC+15") is None
    assert normalize_utc_offset("UTC-13") is None
    assert normalize_utc_offset("UTC+5:99") is None
    assert normalize_utc_offset("UTC+5:20") is None
    assert normalize_utc_offset("foo") is None


def test_format_timezone_offset_and_labels():
    assert format_timezone("UTC+3") == "UTC+3 (Москва)"
    assert format_timezone("UTC+9") == "UTC+9 (Токио)"
    assert format_timezone("UTC-5") == "UTC-5"
    assert format_timezone("UTC+5:30") == "UTC+5:30"
    assert format_timezone("Europe/Moscow") == "UTC+3 (Москва)"


def test_user_timezone_conversion_utc_offset():
    dt = datetime(2026, 8, 13, 13, 40, 31, tzinfo=UTC)
    assert format_user_time(dt, "UTC+9") == "22:40"
    assert format_user_time(dt, "UTC-5") == "08:40"
    assert format_user_time(dt, "UTC+3") == "16:40"


def test_naive_datetime_never_returned():
    parsed = parse_yahoo_datetime("2026-08-13 22:40:31")
    assert parsed.tzinfo is not None
