from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, PrimaryKey


class SentNotification(Base):
    __tablename__ = "sent_notifications"
    __table_args__ = (
        UniqueConstraint("user_auction_id", "kind", "dedup_key", name="uq_sent_notification"),
        Index("ix_sent_notifications_status", "status"),
    )

    id: Mapped[int] = mapped_column(PrimaryKey, primary_key=True)
    user_auction_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user_auctions.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    dedup_key: Mapped[str] = mapped_column(String(128), nullable=False)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user_auction: Mapped["UserAuction"] = relationship()  # noqa: F821
