from datetime import UTC, datetime

import pytest

from app.domain.time import (
    YahooDatetimeParseError,
    format_price,
    format_remaining,
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


def test_format_remaining_days():
    now = datetime(2026, 8, 13, 13, 0, 0, tzinfo=UTC)
    end = datetime(2026, 8, 15, 16, 0, 0, tzinfo=UTC)
    assert format_remaining(end, now) == "2 дн 3 ч"


def test_format_remaining_hours_minutes():
    now = datetime(2026, 8, 13, 13, 0, 0, tzinfo=UTC)
    end = datetime(2026, 8, 13, 14, 25, 0, tzinfo=UTC)
    assert format_remaining(end, now) == "1 ч 25 мин"


def test_format_remaining_hours_only():
    now = datetime(2026, 8, 13, 13, 0, 0, tzinfo=UTC)
    end = datetime(2026, 8, 13, 15, 0, 0, tzinfo=UTC)
    assert format_remaining(end, now) == "2 ч"


def test_format_remaining_minutes():
    now = datetime(2026, 8, 13, 13, 0, 0, tzinfo=UTC)
    end = datetime(2026, 8, 13, 13, 45, 0, tzinfo=UTC)
    assert format_remaining(end, now) == "45 мин"


def test_format_remaining_less_than_minute():
    now = datetime(2026, 8, 13, 13, 0, 0, tzinfo=UTC)
    end = datetime(2026, 8, 13, 13, 0, 30, tzinfo=UTC)
    assert format_remaining(end, now) == "меньше минуты"


def test_format_remaining_past():
    now = datetime(2026, 8, 13, 13, 0, 0, tzinfo=UTC)
    end = datetime(2026, 8, 13, 12, 59, 0, tzinfo=UTC)
    assert format_remaining(end, now) == "завершён"


def test_format_price():
    assert format_price(24000) == "¥24,000"
    assert format_price(0) == "¥0"
    assert format_price(None) == "—"


def test_naive_datetime_never_returned():
    parsed = parse_yahoo_datetime("2026-08-13 22:40:31")
    assert parsed.tzinfo is not None
