from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.domain.diff import diff_states
from app.domain.notifications import NotificationThresholds, evaluate_notifications
from app.domain.polling import PollingIntervals, polling_interval_for
from app.notifications.engine import NotificationEngine
from app.providers import (
    AntiBotError,
    AuctionDataProvider,
    AuctionGoneError,
    PageDataNotFoundError,
    PageDataParseError,
    RateLimitedError,
)
from app.repositories.auctions import AuctionRepository
from app.repositories.snapshots import SnapshotRepository
from app.repositories.user_auctions import UserAuctionRepository
from app.services.state_mapper import state_from_snapshot

logger = structlog.get_logger(__name__)

EnqueueFn = Callable[[str, int], Awaitable[None]]


class MonitoringService:
    """Оркестрация одного poll-цикла аукциона.

    Один вызов poll() = один HTTP-запрос к Yahoo = один возможный fan-out.
    """

    def __init__(
        self,
        session: AsyncSession,
        provider: AuctionDataProvider,
        settings: Settings,
        enqueue_send: EnqueueFn,
    ) -> None:
        self._session = session
        self._provider = provider
        self._settings = settings
        self._enqueue_send = enqueue_send
        self._auctions = AuctionRepository(session)
        self._snapshots = SnapshotRepository(session)
        self._user_auctions = UserAuctionRepository(session)
        self._engine = NotificationEngine(session)
        self._intervals = PollingIntervals.from_settings(settings)
        self._thresholds = NotificationThresholds.from_settings(settings)

    async def poll(self, auction_id: int) -> str:
        auction = await self._auctions.get_by_id(auction_id)
        if auction is None:
            return "not_found"
        if not auction.monitoring_active:
            return "inactive"

        previous_poll_time = auction.last_polled_at or auction.created_at

        try:
            state, raw_data = await self._fetch_state(auction.url)
        except RateLimitedError as exc:
            return await self._handle_error(auction_id, "rate_limited", str(exc))
        except AntiBotError as exc:
            logger.warning("yahoo_antibot", auction_id=auction_id)
            return await self._handle_error(auction_id, "antibot", str(exc), stop=True)
        except AuctionGoneError as exc:
            logger.warning("auction_gone", auction_id=auction_id)
            return await self._handle_error(auction_id, "gone", str(exc), stop=True)
        except PageDataParseError as exc:
            logger.error("page_data_parse_error", auction_id=auction_id, error=str(exc))
            return await self._handle_error(auction_id, "parse_error", str(exc))
        except PageDataNotFoundError as exc:
            return await self._handle_error(auction_id, "no_pagedata", str(exc))

        await self._auctions.clear_error(auction_id)

        latest = await self._snapshots.get_latest(auction_id)
        previous_state = state_from_snapshot(latest) if latest is not None else None
        diff = diff_states(previous_state, state)
        changed = previous_state is None or diff.has_changes

        snapshot_id: int | None = None
        if changed:
            snapshot = await self._snapshots.create(auction_id, state, raw_data=raw_data)
            await self._session.flush()
            snapshot_id = snapshot.id
            await self._auctions.update_from_state(auction, state)

        decisions = evaluate_notifications(
            previous=previous_state,
            current=state,
            diff=diff,
            previous_poll_time=previous_poll_time,
            now=state.observed_at,
            thresholds=self._thresholds,
        )
        watchers = await self._user_auctions.list_watchers(auction_id)
        notification_ids: list[int] = []
        if decisions and watchers:
            notification_ids = await self._engine.create_jobs(
                decisions, watchers, snapshot_id, auction.url
            )

        if state.is_closed:
            auction.monitoring_active = False
            auction.next_poll_at = None
            logger.info("auction_closed", auction_id=auction_id)
        else:
            interval = polling_interval_for(state.until_end, self._intervals)
            auction.next_poll_at = state.observed_at + interval
        auction.last_polled_at = state.observed_at
        await self._session.commit()

        for notification_id in notification_ids:
            await self._enqueue_send("send_notification", notification_id)

        return "polled"

    async def _fetch_state(self, url: str):
        fetch_with_raw = getattr(self._provider, "fetch_state_with_raw", None)
        if fetch_with_raw is not None:
            return await fetch_with_raw(url)
        return await self._provider.get_auction_state(url), None

    async def _handle_error(
        self, auction_id: int, error_type: str, message: str, stop: bool = False
    ) -> str:
        if stop:
            await self._auctions.stop_monitoring(auction_id)
            auction = await self._auctions.get_by_id(auction_id)
            if auction is not None:
                auction.last_error = message[:1000]
            await self._session.commit()
            return f"stopped:{error_type}"

        backoff = self._backoff(await self._current_errors(auction_id) + 1)
        next_poll_at = datetime.now(UTC) + backoff
        errors = await self._auctions.record_error(auction_id, message, next_poll_at)
        if errors >= self._settings.yahoo_max_consecutive_errors:
            logger.error(
                "auction_monitoring_stopped_too_many_errors",
                auction_id=auction_id,
                errors=errors,
            )
            await self._auctions.stop_monitoring(auction_id)
        await self._session.commit()
        return f"error:{error_type}"

    async def _current_errors(self, auction_id: int) -> int:
        auction = await self._auctions.get_by_id(auction_id)
        return auction.consecutive_errors if auction is not None else 0

    def _backoff(self, error_count: int) -> timedelta:
        seconds = min(
            self._settings.yahoo_backoff_base_seconds * (2 ** (error_count - 1)),
            self._settings.yahoo_backoff_max_seconds,
        )
        return timedelta(seconds=seconds)
