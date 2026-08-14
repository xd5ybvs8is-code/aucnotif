
from app.domain.diff import diff_states
from app.domain.notifications import (
    NotificationKind,
    NotificationThresholds,
    dedup_key_for,
    evaluate_notifications,
)
from tests.conftest import make_state, utc

THRESHOLDS = NotificationThresholds()


def _decisions(prev, cur, prev_poll, now):
    return evaluate_notifications(
        previous=prev,
        current=cur,
        diff=diff_states(prev, cur),
        previous_poll_time=prev_poll,
        now=now,
        thresholds=THRESHOLDS,
    )


def test_first_observation_no_notifications():
    cur = make_state()
    decisions = _decisions(None, cur, utc(2026, 8, 13, 12, 0), utc(2026, 8, 13, 12, 2))
    assert decisions == []


def test_30_minute_notification_on_crossing():
    end = utc(2026, 8, 13, 13, 40)
    prev = make_state(end_time=end, observed_at=utc(2026, 8, 13, 13, 9))
    cur = make_state(end_time=end, observed_at=utc(2026, 8, 13, 13, 11))
    decisions = _decisions(prev, cur, prev.observed_at, cur.observed_at)
    kinds = [d.kind for d in decisions]
    assert NotificationKind.T_30M in kinds
    assert NotificationKind.T_15M not in kinds


def test_15_minute_notification_on_crossing():
    end = utc(2026, 8, 13, 13, 40)
    prev = make_state(end_time=end, observed_at=utc(2026, 8, 13, 13, 24))
    cur = make_state(end_time=end, observed_at=utc(2026, 8, 13, 13, 26))
    decisions = _decisions(prev, cur, prev.observed_at, cur.observed_at)
    kinds = [d.kind for d in decisions]
    assert NotificationKind.T_15M in kinds


def test_5_minute_notification_on_crossing():
    end = utc(2026, 8, 13, 13, 40)
    prev = make_state(end_time=end, observed_at=utc(2026, 8, 13, 13, 34))
    cur = make_state(end_time=end, observed_at=utc(2026, 8, 13, 13, 36))
    decisions = _decisions(prev, cur, prev.observed_at, cur.observed_at)
    kinds = [d.kind for d in decisions]
    assert NotificationKind.T_5M in kinds


def test_no_duplicate_timed_notification_within_same_cycle():
    end = utc(2026, 8, 13, 13, 40)
    prev = make_state(end_time=end, observed_at=utc(2026, 8, 13, 13, 9))
    cur = make_state(end_time=end, observed_at=utc(2026, 8, 13, 13, 11))
    decisions = _decisions(prev, cur, prev.observed_at, cur.observed_at)
    assert [d.kind for d in decisions].count(NotificationKind.T_30M) == 1

    # Следующий poll в том же цикле — 30m уже отправлено, не повторяем.
    prev2 = make_state(end_time=end, observed_at=utc(2026, 8, 13, 13, 11))
    cur2 = make_state(end_time=end, observed_at=utc(2026, 8, 13, 13, 13))
    decisions2 = _decisions(prev2, cur2, prev2.observed_at, cur2.observed_at)
    assert NotificationKind.T_30M not in [d.kind for d in decisions2]


def test_crossing_not_in_window_no_notification():
    end = utc(2026, 8, 13, 13, 40)
    prev = make_state(end_time=end, observed_at=utc(2026, 8, 13, 13, 12))
    cur = make_state(end_time=end, observed_at=utc(2026, 8, 13, 13, 13))
    decisions = _decisions(prev, cur, prev.observed_at, cur.observed_at)
    assert decisions == []


def test_change_notification():
    prev = make_state(current_price=24000, bid_count=7, observed_at=utc(2026, 8, 13, 13, 0))
    cur = make_state(current_price=25000, bid_count=8, observed_at=utc(2026, 8, 13, 13, 1))
    decisions = _decisions(prev, cur, prev.observed_at, cur.observed_at)
    kinds = [d.kind for d in decisions]
    assert NotificationKind.CHANGE in kinds


def test_extension_notification():
    prev = make_state(end_time=utc(2026, 8, 13, 13, 40), observed_at=utc(2026, 8, 13, 13, 38))
    cur = make_state(end_time=utc(2026, 8, 13, 13, 45), observed_at=utc(2026, 8, 13, 13, 39))
    decisions = _decisions(prev, cur, prev.observed_at, cur.observed_at)
    kinds = [d.kind for d in decisions]
    assert NotificationKind.EXTENSION in kinds
    assert NotificationKind.CHANGE not in kinds  # продление без ставок


def test_extension_with_bid_change_sends_both():
    prev = make_state(
        end_time=utc(2026, 8, 13, 13, 40),
        current_price=24000,
        observed_at=utc(2026, 8, 13, 13, 38),
    )
    cur = make_state(
        end_time=utc(2026, 8, 13, 13, 45),
        current_price=25000,
        observed_at=utc(2026, 8, 13, 13, 39),
    )
    decisions = _decisions(prev, cur, prev.observed_at, cur.observed_at)
    kinds = [d.kind for d in decisions]
    assert NotificationKind.EXTENSION in kinds
    assert NotificationKind.CHANGE in kinds


def test_timed_notifications_not_refired_after_extension():
    """Продление в 13:38: 5m-точка нового end_time (13:40) уже в прошлом."""
    prev = make_state(end_time=utc(2026, 8, 13, 13, 40), observed_at=utc(2026, 8, 13, 13, 36))
    cur = make_state(end_time=utc(2026, 8, 13, 13, 45), observed_at=utc(2026, 8, 13, 13, 38))
    decisions = _decisions(prev, cur, prev.observed_at, cur.observed_at)
    kinds = [d.kind for d in decisions]
    assert NotificationKind.T_5M not in kinds
    assert NotificationKind.EXTENSION in kinds


def test_closed_notification():
    prev = make_state(is_closed=False, end_time=utc(2026, 8, 13, 13, 40), observed_at=utc(2026, 8, 13, 13, 39))
    cur = make_state(is_closed=True, has_winner=True, end_time=utc(2026, 8, 13, 13, 40), observed_at=utc(2026, 8, 13, 13, 41))
    decisions = _decisions(prev, cur, prev.observed_at, cur.observed_at)
    kinds = [d.kind for d in decisions]
    assert NotificationKind.CLOSED in kinds
    assert NotificationKind.CHANGE not in kinds


def test_dedup_key_timed_uses_end_time():
    end = utc(2026, 8, 13, 13, 40)
    decision = evaluate_notifications(
        previous=make_state(end_time=end, observed_at=utc(2026, 8, 13, 13, 9)),
        current=make_state(end_time=end, observed_at=utc(2026, 8, 13, 13, 11)),
        diff=diff_states(
            make_state(end_time=end, observed_at=utc(2026, 8, 13, 13, 9)),
            make_state(end_time=end, observed_at=utc(2026, 8, 13, 13, 11)),
        ),
        previous_poll_time=utc(2026, 8, 13, 13, 9),
        now=utc(2026, 8, 13, 13, 11),
        thresholds=THRESHOLDS,
    )[0]
    key = dedup_key_for(decision, snapshot_id=None)
    assert key == end.isoformat()


def test_dedup_key_change_uses_snapshot_id():
    decision = evaluate_notifications(
        previous=make_state(current_price=24000, observed_at=utc(2026, 8, 13, 13, 0)),
        current=make_state(current_price=25000, observed_at=utc(2026, 8, 13, 13, 1)),
        diff=diff_states(
            make_state(current_price=24000, observed_at=utc(2026, 8, 13, 13, 0)),
            make_state(current_price=25000, observed_at=utc(2026, 8, 13, 13, 1)),
        ),
        previous_poll_time=utc(2026, 8, 13, 13, 0),
        now=utc(2026, 8, 13, 13, 1),
        thresholds=THRESHOLDS,
    )[0]
    assert dedup_key_for(decision, snapshot_id=42) == "42"
