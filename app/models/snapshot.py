from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, Index, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, PrimaryKey


class AuctionSnapshot(Base):
    __tablename__ = "auction_snapshots"
    __table_args__ = (
        Index("ix_snapshots_auction_observed", "auction_id", "observed_at"),
    )

    id: Mapped[int] = mapped_column(PrimaryKey, primary_key=True)
    auction_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("auctions.id", ondelete="CASCADE"), nullable=False
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    current_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bid_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    buy_now_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_closed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    has_winner: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    new_bid: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    raw_data: Mapped[dict | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )

    auction: Mapped["Auction"] = relationship(back_populates="snapshots")  # noqa: F821
