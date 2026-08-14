from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.config import Settings
from app.models import Auction, AuctionSnapshot, SentNotification, User, UserAuction
from app.providers.base import AntiBotError, RateLimitedError
from app.services.monitoring_service import MonitoringService
from tests.conftest import make_state
from tests.integration.test_auction_service import FakeProvider

URL = "https://page.auctions.yahoo.co.jp/jp/auction/f1240539796"


async def _setup(db_session, provider):
    user = User(telegram_id=111, timezone="Europe/London", language="ru")
    db_session.add(user)
    await db_session.flush()
    auction = Auction(
        external_id="f1240539796",
        url=URL,
        title="Test",
        current_price=24000,
        bid_count=7,
        end_time=datetime(2026, 8, 13, 13, 40, tzinfo=UTC),
        is_closed=False,
        monitoring_active=True,
        next_poll_at=datetime.now(UTC),
        last_polled_at=datetime.now(UTC) - timedelta(minutes=2),
    )
    db_session.add(auction)
    await db_session.flush()
    db_session.add(UserAuction(user_id=user.id, auction_id=auction.id))
    await db_session.flush()
    return user, auction


def _make_service(db_session, provider, enqueued):
    return MonitoringService(
        db_session,
        provider,
        Settings(),
        enqueue_send=lambda name, notification_id: _record(enqueued, name, notification_id),
    )


async def _record(enqueued, name, notification_id):
    enqueued.append(notification_id)


async def _count(db_session, model):
    return (await db_session.execute(select(func.count()).select_from(model))).scalar_one()


async def test_full_poll_cycle_with_change(db_session):
    provider = FakeProvider()
    enqueued = []
    user, auction = await _setup(db_session, provider)

    first = make_state(observed_at=datetime.now(UTC))
    provider.push(first)
    service = _make_service(db_session, provider, enqueued)
    result = await service.poll(auction.id)
    assert result == "polled"
    assert await _count(db_session, AuctionSnapshot) == 1
    assert enqueued == []  # первое наблюдение — без уведомлений

    changed = make_state(
        current_price=25000,
        bid_count=8,
        observed_at=datetime.now(UTC),
    )
    provider.push(changed)
    enqueued.clear()
    result = await service.poll(auction.id)
    assert result == "polled"
    assert await _count(db_session, AuctionSnapshot) == 2
    assert len(enqueued) == 1

    notifications = (
        await db_session.execute(select(SentNotification))
    ).scalars().all()
    assert len(notifications) == 1
    assert notifications[0].kind == "change"
    assert notifications[0].text is not None
    assert "¥25,000" in notifications[0].text


async def test_unchanged_state_no_new_notifications(db_session):
    provider = FakeProvider()
    enqueued = []
    user, auction = await _setup(db_session, provider)

    state = make_state(observed_at=datetime.now(UTC))
    provider.push(state)
    provider.push(make_state(observed_at=datetime.now(UTC)))
    service = _make_service(db_session, provider, enqueued)
    await service.poll(auction.id)
    enqueued.clear()
    await service.poll(auction.id)
    assert enqueued == []
    assert await _count(db_session, AuctionSnapshot) == 1
    assert await _count(db_session, SentNotification) == 0


async def test_extension_notification_cycle(db_session):
    provider = FakeProvider()
    enqueued = []
    user, auction = await _setup(db_session, provider)

    base = make_state(
        end_time=datetime(2026, 8, 13, 13, 40, tzinfo=UTC),
        observed_at=datetime.now(UTC),
    )
    provider.push(base)
    service = _make_service(db_session, provider, enqueued)
    await service.poll(auction.id)

    extended = make_state(
        end_time=datetime(2026, 8, 13, 13, 45, tzinfo=UTC),
        observed_at=datetime.now(UTC),
    )
    provider.push(extended)
    enqueued.clear()
    await service.poll(auction.id)

    notifications = (
        await db_session.execute(select(SentNotification))
    ).scalars().all()
    kinds = [n.kind for n in notifications]
    assert "extension" in kinds
    assert len(enqueued) == 1

    auction_db = (
        await db_session.execute(select(Auction).where(Auction.id == auction.id))
    ).scalar_one()
    assert auction_db.end_time == extended.end_time  # end_time обновлён


async def test_closed_auction_stops_monitoring(db_session):
    provider = FakeProvider()
    enqueued = []
    user, auction = await _setup(db_session, provider)

    provider.push(make_state(observed_at=datetime.now(UTC)))
    service = _make_service(db_session, provider, enqueued)
    await service.poll(auction.id)

    closed = make_state(is_closed=True, has_winner=True, observed_at=datetime.now(UTC))
    provider.push(closed)
    enqueued.clear()
    result = await service.poll(auction.id)
    assert result == "polled"

    auction_db = (
        await db_session.execute(select(Auction).where(Auction.id == auction.id))
    ).scalar_one()
    assert auction_db.monitoring_active is False
    assert auction_db.is_closed is True

    notifications = (
        await db_session.execute(select(SentNotification))
    ).scalars().all()
    assert [n.kind for n in notifications] == ["closed"]


async def test_rate_limited_backoff(db_session):
    provider = FakeProvider()
    enqueued = []
    user, auction = await _setup(db_session, provider)

    provider.exc = RateLimitedError(429, "rate limited")
    service = _make_service(db_session, provider, enqueued)
    result = await service.poll(auction.id)
    assert result == "error:rate_limited"

    auction_db = (
        await db_session.execute(select(Auction).where(Auction.id == auction.id))
    ).scalar_one()
    assert auction_db.consecutive_errors == 1
    assert auction_db.next_poll_at > datetime.now(UTC)  # backoff в будущем
    assert auction_db.monitoring_active is True
    assert await _count(db_session, AuctionSnapshot) == 0


async def test_antibot_stops_monitoring(db_session):
    provider = FakeProvider()
    enqueued = []
    user, auction = await _setup(db_session, provider)

    provider.exc = AntiBotError("captcha")
    service = _make_service(db_session, provider, enqueued)
    result = await service.poll(auction.id)
    assert result == "stopped:antibot"

    auction_db = (
        await db_session.execute(select(Auction).where(Auction.id == auction.id))
    ).scalar_one()
    assert auction_db.monitoring_active is False


async def test_30m_notification_for_multiple_users(db_session):
    provider = FakeProvider()
    enqueued = []
    user, auction = await _setup(db_session, provider)

    user2 = User(telegram_id=222, timezone="Europe/London", language="ru")
    db_session.add(user2)
    await db_session.flush()
    db_session.add(UserAuction(user_id=user2.id, auction_id=auction.id))
    await db_session.flush()

    now = datetime.now(UTC)
    end = now + timedelta(minutes=31)
    provider.push(make_state(end_time=end, observed_at=now))
    service = _make_service(db_session, provider, enqueued)
    await service.poll(auction.id)

    now2 = now + timedelta(minutes=2)
    provider.push(make_state(end_time=end, observed_at=now2))
    enqueued.clear()
    await service.poll(auction.id)

    notifications = (
        await db_session.execute(select(SentNotification))
    ).scalars().all()
    assert len(notifications) == 2  # fan-out обоим пользователям
    assert all(n.kind == "30m" for n in notifications)
    assert len(enqueued) == 2
    assert provider.calls == 2  # Yahoo опрошен по одному разу на poll
