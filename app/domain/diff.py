from pydantic import BaseModel, Field

from app.domain.auction_state import AuctionState


class AuctionStateDiff(BaseModel):
    price_changed: bool = False
    bid_count_changed: bool = False
    end_time_changed: bool = False
    buy_now_price_changed: bool = False
    is_closed_changed: bool = False
    winner_changed: bool = False
    new_bid_detected: bool = False

    previous: AuctionState | None = None
    current: AuctionState | None = None

    @property
    def has_changes(self) -> bool:
        return (
            self.price_changed
            or self.bid_count_changed
            or self.end_time_changed
            or self.buy_now_price_changed
            or self.is_closed_changed
            or self.winner_changed
        )

    @property
    def extension_detected(self) -> bool:
        """Аукцион продлён: end_time сдвинулся в будущее."""
        if not self.end_time_changed or self.previous is None or self.current is None:
            return False
        if self.previous.end_time is None or self.current.end_time is None:
            return False
        return self.current.end_time > self.previous.end_time


class DiffConfig(BaseModel):
    """Порог, при котором изменение current_price считается значимым."""

    price_change_threshold: int = Field(default=1, ge=0)


def diff_states(
    previous: AuctionState | None,
    current: AuctionState,
    config: DiffConfig | None = None,
) -> AuctionStateDiff:
    """Сравнивает два состояния.

    previous=None означает первое наблюдение: базовый снимок без diff-изменений.
    """
    cfg = config or DiffConfig()
    diff = AuctionStateDiff(previous=previous, current=current)
    if previous is None:
        return diff

    if previous.current_price is not None and current.current_price is not None:
        diff.price_changed = (
            abs(current.current_price - previous.current_price) >= cfg.price_change_threshold
        )
    elif previous.current_price != current.current_price:
        diff.price_changed = True

    diff.bid_count_changed = previous.bid_count != current.bid_count
    diff.end_time_changed = previous.end_time != current.end_time
    diff.buy_now_price_changed = previous.buy_now_price != current.buy_now_price
    diff.is_closed_changed = previous.is_closed != current.is_closed
    diff.winner_changed = previous.has_winner != current.has_winner

    diff.new_bid_detected = bool(
        current.new_bid
        or (
            previous.bid_count is not None
            and current.bid_count is not None
            and current.bid_count > previous.bid_count
        )
        or (
            previous.current_price is not None
            and current.current_price is not None
            and current.current_price != previous.current_price
        )
    )
    return diff
