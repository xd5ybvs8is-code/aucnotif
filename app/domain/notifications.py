from datetime import datetime, timedelta
from enum import StrEnum

from pydantic import BaseModel

from app.domain.auction_state import AuctionState
from app.domain.diff import AuctionStateDiff


class NotificationKind(StrEnum):
    T_30M = "30m"
    T_15M = "15m"
    T_5M = "5m"
    CHANGE = "change"
    EXTENSION = "extension"
    CLOSED = "closed"


class NotificationThresholds(BaseModel):
    t_30m: timedelta = timedelta(minutes=30)
    t_15m: timedelta = timedelta(minutes=15)
    t_5m: timedelta = timedelta(minutes=5)

    @classmethod
    def from_settings(cls, settings) -> "NotificationThresholds":
        return cls(
            t_30m=timedelta(seconds=settings.notify_30m_before_seconds),
            t_15m=timedelta(seconds=settings.notify_15m_before_seconds),
            t_5m=timedelta(seconds=settings.notify_5m_before_seconds),
        )


class NotificationDecision(BaseModel):
    kind: NotificationKind
    previous: AuctionState | None = None
    current: AuctionState | None = None


def evaluate_notifications(
    previous: AuctionState | None,
    current: AuctionState,
    diff: AuctionStateDiff,
    previous_poll_time: datetime,
    now: datetime,
    thresholds: NotificationThresholds,
) -> list[NotificationDecision]:
    """Чистая логика: какие уведомления нужно отправить после poll'а.

    Timed-уведомления (30/15/5 минут) срабатывают, только если момент
    `end_time - T` попал между предыдущим и текущим опросом — это даёт
    идемпотентность и корректную работу после продления аукциона.
    """
    decisions: list[NotificationDecision] = []

    if previous is None:
        # Первое наблюдение — только базовый снимок, без уведомлений.
        return decisions

    if current.end_time is not None:
        for kind, threshold in (
            (NotificationKind.T_30M, thresholds.t_30m),
            (NotificationKind.T_15M, thresholds.t_15m),
            (NotificationKind.T_5M, thresholds.t_5m),
        ):
            crossing = current.end_time - threshold
            if previous_poll_time < crossing <= now:
                decisions.append(
                    NotificationDecision(kind=kind, previous=previous, current=current)
                )

    if diff.is_closed_changed and current.is_closed:
        decisions.append(
            NotificationDecision(kind=NotificationKind.CLOSED, previous=previous, current=current)
        )
    elif diff.extension_detected:
        decisions.append(
            NotificationDecision(kind=NotificationKind.EXTENSION, previous=previous, current=current)
        )
        if diff.has_changes and (
            diff.price_changed or diff.bid_count_changed or diff.new_bid_detected
        ):
            decisions.append(
                NotificationDecision(kind=NotificationKind.CHANGE, previous=previous, current=current)
            )
    elif diff.has_changes:
        decisions.append(
            NotificationDecision(kind=NotificationKind.CHANGE, previous=previous, current=current)
        )

    return decisions


def dedup_key_for(decision: NotificationDecision, snapshot_id: int | None = None) -> str:
    """Стабильный ключ идемпотентности уведомления.

    Timed-уведомления ключуются по текущему end_time — продление аукциона
    создаёт новый «цикл окончания», старые ключи не конфликтуют.
    Change/extension/closed ключуются по snapshot id.
    """
    if decision.kind in (NotificationKind.T_30M, NotificationKind.T_15M, NotificationKind.T_5M):
        if decision.current is None or decision.current.end_time is None:
            raise ValueError("timed notification requires current.end_time")
        return decision.current.end_time.isoformat()
    if snapshot_id is None:
        raise ValueError("snapshot_id required for non-timed notification")
    return str(snapshot_id)
