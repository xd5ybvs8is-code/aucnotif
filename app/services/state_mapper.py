from app.domain.auction_state import AuctionState
from app.domain.time import ensure_aware
from app.models import Auction, AuctionSnapshot


def state_from_snapshot(snapshot: AuctionSnapshot) -> AuctionState:
    return AuctionState(
        auction_id="",
        current_price=snapshot.current_price,
        bid_count=snapshot.bid_count,
        end_time=ensure_aware(snapshot.end_time),
        buy_now_price=snapshot.buy_now_price,
        is_closed=bool(snapshot.is_closed),
        has_winner=snapshot.has_winner,
        new_bid=snapshot.new_bid,
        observed_at=ensure_aware(snapshot.observed_at) or snapshot.observed_at,
    )


def state_from_auction(auction: Auction) -> AuctionState:
    return AuctionState(
        auction_id=auction.external_id,
        title=auction.title,
        current_price=auction.current_price,
        bid_count=auction.bid_count,
        start_time=ensure_aware(auction.start_time),
        end_time=ensure_aware(auction.end_time),
        buy_now_price=auction.buy_now_price,
        quantity=auction.quantity,
        is_store=auction.is_store,
        is_closed=auction.is_closed,
        has_winner=auction.has_winner,
    )
