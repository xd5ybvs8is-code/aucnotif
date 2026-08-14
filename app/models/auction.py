from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, PrimaryKey, TimestampMixin


class Auction(Base, TimestampMixin):
    __tablename__ = "auctions"
    __table_args__ = (
        Index("ix_auctions_monitoring_next_poll", "monitoring_active", "next_poll_at"),
        Index("ix_auctions_closed", "is_closed"),
    )

    id: Mapped[int] = mapped_column(PrimaryKey, primary_key=True)
    external_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)

    current_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bid_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    buy_now_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_store: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_closed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    has_winner: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    monitoring_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    next_poll_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    consecutive_errors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    user_auctions: Mapped[list["UserAuction"]] = relationship(back_populates="auction")  # noqa: F821
    snapshots: Mapped[list["AuctionSnapshot"]] = relationship(back_populates="auction")  # noqa: F821
