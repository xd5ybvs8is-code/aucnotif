from datetime import timedelta

from pydantic import BaseModel


class PollingIntervals(BaseModel):
    gt_24h: timedelta = timedelta(hours=6)
    from_6h_to_24h: timedelta = timedelta(minutes=30)
    from_1h_to_6h: timedelta = timedelta(minutes=10)
    from_30m_to_60m: timedelta = timedelta(minutes=2)
    from_15m_to_30m: timedelta = timedelta(minutes=1)
    lt_15m: timedelta = timedelta(minutes=1)

    @classmethod
    def from_settings(cls, settings) -> "PollingIntervals":
        return cls(
            gt_24h=timedelta(seconds=settings.poll_interval_gt_24h),
            from_6h_to_24h=timedelta(seconds=settings.poll_interval_6_24h),
            from_1h_to_6h=timedelta(seconds=settings.poll_interval_1_6h),
            from_30m_to_60m=timedelta(seconds=settings.poll_interval_30_60m),
            from_15m_to_30m=timedelta(seconds=settings.poll_interval_15_30m),
            lt_15m=timedelta(seconds=settings.poll_interval_lt_15m),
        )


def polling_interval_for(
    until_end: timedelta | None, intervals: PollingIntervals
) -> timedelta:
    """Adaptive polling: чем ближе окончание, тем чаще опрос.

    Сравнение идёт по верхней границе бакета; отрицательный until_end
    (аукцион уже должен был закончиться) обрабатывается как < 15m — систему
    нужно как можно скорее проверить, закрылся ли аукцион.
    None (end_time неизвестен) → средний интервал 1-6h.
    """
    if until_end is None:
        return intervals.from_1h_to_6h
    if until_end > timedelta(hours=24):
        return intervals.gt_24h
    if until_end > timedelta(hours=6):
        return intervals.from_6h_to_24h
    if until_end > timedelta(hours=1):
        return intervals.from_1h_to_6h
    if until_end > timedelta(minutes=30):
        return intervals.from_30m_to_60m
    if until_end > timedelta(minutes=15):
        return intervals.from_15m_to_30m
    return intervals.lt_15m
