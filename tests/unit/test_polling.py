from datetime import timedelta

from app.domain.polling import PollingIntervals, polling_interval_for


def test_buckets():
    i = PollingIntervals()
    assert polling_interval_for(timedelta(hours=48), i) == timedelta(hours=6)
    assert polling_interval_for(timedelta(hours=24), i) == timedelta(minutes=30)
    assert polling_interval_for(timedelta(hours=10), i) == timedelta(minutes=30)
    assert polling_interval_for(timedelta(hours=6), i) == timedelta(minutes=10)
    assert polling_interval_for(timedelta(hours=2), i) == timedelta(minutes=10)
    assert polling_interval_for(timedelta(hours=1), i) == timedelta(minutes=2)
    assert polling_interval_for(timedelta(minutes=45), i) == timedelta(minutes=2)
    assert polling_interval_for(timedelta(minutes=30), i) == timedelta(minutes=1)
    assert polling_interval_for(timedelta(minutes=20), i) == timedelta(minutes=1)
    assert polling_interval_for(timedelta(minutes=15), i) == timedelta(minutes=1)
    assert polling_interval_for(timedelta(minutes=5), i) == timedelta(minutes=1)


def test_past_end_time_aggressive():
    i = PollingIntervals()
    assert polling_interval_for(timedelta(minutes=-5), i) == timedelta(minutes=1)


def test_unknown_end_time():
    i = PollingIntervals()
    assert polling_interval_for(None, i) == timedelta(minutes=10)
