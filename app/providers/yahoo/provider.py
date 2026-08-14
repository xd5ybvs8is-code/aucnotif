from datetime import UTC, datetime

import structlog
from pydantic import ValidationError

from app.domain.auction_state import AuctionState
from app.infrastructure.metrics import PAGE_DATA_PARSE_ERRORS
from app.providers.base import PageDataNotFoundError, PageDataParseError
from app.providers.yahoo.client import YahooHttpClient
from app.providers.yahoo.extractor import PageDataExtractionError, PageDataExtractor
from app.schemas.yahoo import PageData, YahooAuctionData

logger = structlog.get_logger(__name__)


class YahooAuctionProvider:
    """Получает HTML страницы аукциона, извлекает pageData и нормализует.

    Pipeline: HTTP GET → HTML → extract pageData → parse → validate → AuctionState.
    """

    def __init__(
        self,
        http_client: YahooHttpClient,
        extractor: PageDataExtractor | None = None,
        store_raw_data: bool = False,
    ) -> None:
        self._http = http_client
        self._extractor = extractor or PageDataExtractor()
        self._store_raw_data = store_raw_data

    async def get_auction_state(self, url: str) -> AuctionState:
        state, _ = await self.fetch_state_with_raw(url)
        return state

    async def fetch_state_with_raw(self, url: str) -> tuple[AuctionState, dict | None]:
        html = await self._http.fetch_html(url)
        return self.parse_auction_state(html, url)

    def parse_auction_state(self, html: str, url: str) -> tuple[AuctionState, dict | None]:
        try:
            raw_page_data = self._extractor.extract(html)
        except PageDataExtractionError as exc:
            PAGE_DATA_PARSE_ERRORS.labels(reason="not_found").inc()
            raise PageDataNotFoundError(f"pageData not found for {url}") from exc

        try:
            page_data = PageData.model_validate(raw_page_data)
            if page_data.items is None:
                raise PageDataParseError("pageData.items is missing")
            yahoo_data = YahooAuctionData.from_items(page_data.items)
        except (ValidationError, ValueError) as exc:
            PAGE_DATA_PARSE_ERRORS.labels(reason="validation").inc()
            logger.warning("page_data_validation_failed", url=url, error=str(exc))
            raise PageDataParseError(f"invalid pageData for {url}: {exc}") from exc

        observed_at = datetime.now(UTC)
        state = AuctionState(
            auction_id=yahoo_data.product_id,
            title=yahoo_data.product_name,
            current_price=yahoo_data.price,
            bid_count=yahoo_data.bids,
            start_time=yahoo_data.starttime,
            end_time=yahoo_data.endtime,
            buy_now_price=yahoo_data.win_price,
            quantity=yahoo_data.quantity,
            is_store=yahoo_data.is_store,
            is_closed=bool(yahoo_data.is_closed),
            has_winner=yahoo_data.has_winner,
            new_bid=yahoo_data.new_bid,
            observed_at=observed_at,
        )
        logger.info(
            "auction_state_parsed",
            auction_id=state.auction_id,
            is_closed=state.is_closed,
            end_time=str(state.end_time),
        )
        return state, raw_page_data if self._store_raw_data else None

    async def close(self) -> None:
        await self._http.close()
