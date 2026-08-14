
from app.domain.diff import DiffConfig, diff_states
from tests.conftest import make_state, utc


def test_no_changes():
    prev = make_state(observed_at=utc(2026, 8, 13, 12, 0))
    cur = make_state(observed_at=utc(2026, 8, 13, 12, 2))
    diff = diff_states(prev, cur)
    assert not diff.has_changes
    assert not diff.price_changed
    assert not diff.bid_count_changed
    assert not diff.end_time_changed
    assert not diff.new_bid_detected


def test_first_observation_is_baseline():
    cur = make_state()
    diff = diff_states(None, cur)
    assert not diff.has_changes
    assert not diff.new_bid_detected


def test_price_change():
    prev = make_state(current_price=24000, observed_at=utc(2026, 8, 13, 12, 0))
    cur = make_state(current_price=25000, observed_at=utc(2026, 8, 13, 12, 2))
    diff = diff_states(prev, cur)
    assert diff.price_changed
    assert diff.has_changes
    assert diff.new_bid_detected  # цена изменилась → новая ставка


def test_bid_count_change():
    prev = make_state(bid_count=7, observed_at=utc(2026, 8, 13, 12, 0))
    cur = make_state(bid_count=8, observed_at=utc(2026, 8, 13, 12, 2))
    diff = diff_states(prev, cur)
    assert diff.bid_count_changed
    assert diff.new_bid_detected


def test_end_time_change():
    prev = make_state(end_time=utc(2026, 8, 13, 13, 40), observed_at=utc(2026, 8, 13, 12, 0))
    cur = make_state(end_time=utc(2026, 8, 13, 13, 45), observed_at=utc(2026, 8, 13, 12, 2))
    diff = diff_states(prev, cur)
    assert diff.end_time_changed
    assert diff.has_changes


def test_extension_detected():
    prev = make_state(end_time=utc(2026, 8, 13, 13, 40), observed_at=utc(2026, 8, 13, 13, 38))
    cur = make_state(end_time=utc(2026, 8, 13, 13, 45), observed_at=utc(2026, 8, 13, 13, 39))
    diff = diff_states(prev, cur)
    assert diff.extension_detected


def test_end_time_shift_back_is_not_extension():
    prev = make_state(end_time=utc(2026, 8, 13, 13, 45), observed_at=utc(2026, 8, 13, 13, 38))
    cur = make_state(end_time=utc(2026, 8, 13, 13, 40), observed_at=utc(2026, 8, 13, 13, 39))
    diff = diff_states(prev, cur)
    assert diff.end_time_changed
    assert not diff.extension_detected


def test_new_bid_flag_alone_triggers_detection():
    prev = make_state(new_bid=False, bid_count=7, current_price=24000)
    cur = make_state(new_bid=True, bid_count=7, current_price=24000)
    diff = diff_states(prev, cur)
    assert diff.new_bid_detected
    assert not diff.has_changes  # флаг — только вспомогательный сигнал


def test_buy_now_price_change():
    prev = make_state(buy_now_price=29000)
    cur = make_state(buy_now_price=28000)
    diff = diff_states(prev, cur)
    assert diff.buy_now_price_changed
    assert diff.has_changes


def test_closed_transition():
    prev = make_state(is_closed=False)
    cur = make_state(is_closed=True, has_winner=True)
    diff = diff_states(prev, cur)
    assert diff.is_closed_changed
    assert diff.winner_changed
    assert diff.has_changes


def test_price_threshold_config():
    prev = make_state(current_price=24000)
    cur = make_state(current_price=24001)
    assert not diff_states(prev, cur, DiffConfig(price_change_threshold=100)).price_changed
    assert diff_states(prev, cur, DiffConfig(price_change_threshold=1)).price_changed
