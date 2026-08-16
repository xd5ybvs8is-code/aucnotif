from collections import deque

from sqlalchemy import func, select

from app.config import Settings
from app.models import Auction, SentNotification, User, UserAuction
from app.repositories.notifications import NotificationRepository
from app.services.auction_service import AuctionService
from tests.conftest import make_state


class FakeProvider:
    """Мок Yahoo-провайдера для интеграционных тестов."""

    def __init__(self):
        self.states = deque()
        self.exc = None
        self.calls = 0
        self.last_url = None

    def push(self, state):
        self.states.append(state)

    async def get_auction_state(self, url):
        self.calls += 1
        self.last_url = url
        if self.exc is not None:
            raise self.exc
        return self.states.popleft()


async def test_add_watch_closed_auction_not_added(db_session):
    provider = FakeProvider()
    provider.push(make_state(is_closed=True, has_winner=True))
    service = AuctionService(db_session, provider, Settings())
    url = "https://page.auctions.yahoo.co.jp/jp/auction/f1240539796"

    result, _user = await service.add_watch(111, url)
    assert result.already_watched is False
    assert result.auction.is_closed is True

    link_count = (
        await db_session.execute(select(func.count()).select_from(UserAuction))
    ).scalar_one()
    assert link_count == 0

    auction = (
        await db_session.execute(select(Auction).where(Auction.external_id == "f1240539796"))
    ).scalar_one()
    assert auction.monitoring_active is False


async def test_add_auction_twice_no_duplicates(db_session):
    provider = FakeProvider()
    provider.push(make_state())
    service = AuctionService(db_session, provider, Settings())

    result1, _user = await service.add_watch(111, "https://page.auctions.yahoo.co.jp/jp/auction/f1240539796")
    assert result1.already_watched is False

    result2, _user = await service.add_watch(111, "https://page.auctions.yahoo.co.jp/jp/auction/f1240539796")
    assert result2.already_watched is True
    assert result1.auction.id == result2.auction.id

    count = (
        await db_session.execute(select(func.count()).select_from(Auction))
    ).scalar_one()
    link_count = (
        await db_session.execute(select(func.count()).select_from(UserAuction))
    ).scalar_one()
    assert count == 1
    assert link_count == 1
    assert provider.calls == 1  # Yahoo опрошен только один раз


async def test_multiple_users_watch_same_auction(db_session):
    provider = FakeProvider()
    provider.push(make_state())
    service = AuctionService(db_session, provider, Settings())
    url = "https://page.auctions.yahoo.co.jp/jp/auction/f1240539796"

    for telegram_id in (111, 222, 333):
        await service.add_watch(telegram_id, url)

    count = (await db_session.execute(select(func.count()).select_from(Auction))).scalar_one()
    link_count = (await db_session.execute(select(func.count()).select_from(UserAuction))).scalar_one()
    user_count = (await db_session.execute(select(func.count()).select_from(User))).scalar_one()
    assert count == 1
    assert link_count == 3
    assert user_count == 3
    assert provider.calls == 1  # один polling stream на аукцион


async def test_remove_watch_keeps_other_users(db_session):
    provider = FakeProvider()
    provider.push(make_state())
    service = AuctionService(db_session, provider, Settings())
    url = "https://page.auctions.yahoo.co.jp/jp/auction/f1240539796"

    await service.add_watch(111, url)
    await service.add_watch(222, url)

    result = await service.remove_watch(111, "f1240539796")
    assert result == "removed"

    link_count = (await db_session.execute(select(func.count()).select_from(UserAuction))).scalar_one()
    assert link_count == 1

    auction = (
        await db_session.execute(select(Auction).where(Auction.external_id == "f1240539796"))
    ).scalar_one()
    assert auction.monitoring_active is True  # User 222 ещё следит


async def test_set_label(db_session):
    provider = FakeProvider()
    provider.push(make_state())
    service = AuctionService(db_session, provider, Settings())
    url = "https://page.auctions.yahoo.co.jp/jp/auction/f1240539796"

    await service.add_watch(111, url)

    assert await service.set_label(111, "f1240539796", "Моя приставка") is True
    link = (await db_session.execute(select(UserAuction))).scalar_one()
    assert link.label == "Моя приставка"

    assert await service.set_label(111, "f1240539796", None) is True
    await db_session.refresh(link)
    assert link.label is None

    assert await service.set_label(999, "f1240539796", "x") is None
    assert await service.set_label(111, "missing", "x") is None


async def test_remove_watch_last_user_grace_period(db_session):
    provider = FakeProvider()
    provider.push(make_state())
    service = AuctionService(db_session, provider, Settings())
    url = "https://page.auctions.yahoo.co.jp/jp/auction/f1240539796"

    await service.add_watch(111, url)
    await service.remove_watch(111, "f1240539796")

    auction = (
        await db_session.execute(select(Auction).where(Auction.external_id == "f1240539796"))
    ).scalar_one()
    assert auction.monitoring_active is True
    assert auction.next_poll_at is not None  # отложен на grace period


async def test_duplicate_notification_prevention(db_session):
    repo = NotificationRepository(db_session)
    user = User(telegram_id=1)
    db_session.add(user)
    await db_session.flush()
    auction = Auction(
        external_id="dup-test",
        url="https://page.auctions.yahoo.co.jp/jp/auction/dup-test",
        title="Dup",
        monitoring_active=True,
    )
    db_session.add(auction)
    await db_session.flush()
    link = UserAuction(user_id=user.id, auction_id=auction.id)
    db_session.add(link)
    await db_session.flush()

    first = await repo.claim(link.id, "30m", "2026-08-13T13:40:31+00:00")
    second = await repo.claim(link.id, "30m", "2026-08-13T13:40:31+00:00")
    other_kind = await repo.claim(link.id, "15m", "2026-08-13T13:40:31+00:00")
    other_cycle = await repo.claim(link.id, "30m", "2026-08-13T13:45:00+00:00")

    assert first is not None
    assert second is None  # дубль не создан
    assert other_kind is not None
    assert other_cycle is not None  # новый цикл окончания — новое уведомление

    count = (
        await db_session.execute(select(func.count()).select_from(SentNotification))
    ).scalar_one()
    assert count == 3
