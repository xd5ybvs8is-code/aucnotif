from app.domain.notifications import NotificationDecision, NotificationKind
from app.notifications.renderer import NotificationRenderer
from tests.conftest import make_state, utc


def _decision(kind, prev=None, cur=None):
    return NotificationDecision(kind=kind, previous=prev, current=cur)


def test_added_message():
    state = make_state(end_time=utc(2026, 8, 13, 13, 40))
    text = NotificationRenderer().render_added(state, "https://example.com/x")
    assert "✅ Аукцион добавлен" in text
    assert "¥24,000" in text
    assert "Открыть аукцион" in text


def test_change_only_changed_fields():
    prev = make_state(current_price=24000, bid_count=7, end_time=utc(2026, 8, 13, 13, 40))
    cur = make_state(current_price=25000, bid_count=7, end_time=utc(2026, 8, 13, 13, 40))
    text = NotificationRenderer().render(
        _decision(NotificationKind.CHANGE, prev, cur), "https://example.com/x"
    )
    assert "¥24,000 → ¥25,000" in text
    assert "Ставок" not in text  # bid_count не менялся
    assert "До конца" not in text  # end_time не менялся


def test_change_with_extension_fields():
    prev = make_state(
        current_price=24000, bid_count=7, end_time=utc(2026, 8, 13, 13, 40)
    )
    cur = make_state(
        current_price=25000, bid_count=8, end_time=utc(2026, 8, 13, 13, 45)
    )
    text = NotificationRenderer().render(
        _decision(NotificationKind.CHANGE, prev, cur), "https://example.com/x"
    )
    assert "¥24,000 → ¥25,000" in text
    assert "7 → 8" in text
    assert "До конца" in text


def test_extension_message():
    prev = make_state(end_time=utc(2026, 8, 13, 13, 40))
    cur = make_state(end_time=utc(2026, 8, 13, 13, 45))
    text = NotificationRenderer().render(
        _decision(NotificationKind.EXTENSION, prev, cur), "https://example.com/x"
    )
    assert "Аукцион продлён" in text
    assert "Было:" in text
    assert "Стало:" in text


def test_30m_message():
    state = make_state(end_time=utc(2026, 8, 13, 13, 40))
    text = NotificationRenderer().render(
        _decision(NotificationKind.T_30M, cur=state), "https://example.com/x"
    )
    assert "30 минут" in text
    assert "¥24,000" in text


def test_closed_message():
    state = make_state(is_closed=True, has_winner=True)
    text = NotificationRenderer().render(
        _decision(NotificationKind.CLOSED, cur=state), "https://example.com/x"
    )
    assert "Аукцион завершён" in text
    assert "Победитель определён" in text
