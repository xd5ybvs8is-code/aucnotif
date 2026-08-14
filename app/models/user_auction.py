from sqlalchemy import BigInteger, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, PrimaryKey, TimestampMixin


class UserAuction(Base, TimestampMixin):
    __tablename__ = "user_auctions"
    __table_args__ = (UniqueConstraint("user_id", "auction_id", name="uq_user_auction"),)

    id: Mapped[int] = mapped_column(PrimaryKey, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    auction_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("auctions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    user: Mapped["User"] = relationship(back_populates="user_auctions")  # noqa: F821
    auction: Mapped["Auction"] = relationship(back_populates="user_auctions")  # noqa: F821
