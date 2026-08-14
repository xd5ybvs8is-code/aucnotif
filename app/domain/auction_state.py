from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

UTC = ZoneInfo("UTC")


class AuctionState(BaseModel):
    """Нормализованное состояние аукциона, независимое от Yahoo."""

    auction_id: str = Field(description="Уникальный external id аукциона (Yahoo productID)")
    title: str | None = None
    current_price: int | None = None
    bid_count: int | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    buy_now_price: int | None = None
    quantity: int | None = None
    is_store: bool | None = None
    is_closed: bool = False
    has_winner: bool | None = None
    new_bid: bool | None = None
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def until_end(self) -> timedelta | None:
        if self.end_time is None:
            return None
        return self.end_time - self.observed_at

    def is_equivalent_to(self, other: "AuctionState") -> bool:
        """True, если значимые поля совпадают (наблюдение не считается изменением)."""
        comparable = (
            "current_price",
            "bid_count",
            "start_time",
            "end_time",
            "buy_now_price",
            "quantity",
            "is_store",
            "is_closed",
            "has_winner",
            "new_bid",
            "title",
        )
        return all(getattr(self, f) == getattr(other, f) for f in comparable)
