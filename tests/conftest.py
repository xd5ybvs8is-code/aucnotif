import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.domain.auction_state import AuctionState

FIXTURES_DIR = Path(__file__).parent / "fixtures"

DEFAULT_ITEMS = {
    "productID": "f1240539796",
    "productName": "ニンテンドー3DS コスモブラック",
    "productCategoryID": "2084290227",
    "price": "24000",
    "starttime": "2026-08-12 21:40:31",
    "endtime": "2026-08-13 22:40:31",
    "winPrice": "29000",
    "quantity": "1",
    "bids": "7",
    "isStore": "0",
    "isAdult": "0",
    "isClosed": "0",
    "hasWinner": "0",
    "newBid": "0",
    "enableBooth": "0",
}


def load_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def load_fixture_json(name: str) -> dict:
    return json.loads(load_fixture(name))


def make_html(items: dict | None = None) -> str:
    items = items if items is not None else dict(DEFAULT_ITEMS)
    page_data = {"navigation": {"pageName": "PRODUCT", "isForeign": 1}, "items": items}
    return (
        "<!DOCTYPE html><html><head><meta charset=\"utf-8\"></head><body>"
        f"<script>var pageData = {json.dumps(page_data)};</script>"
        "</body></html>"
    )


def make_state(**overrides) -> AuctionState:
    defaults = dict(
        auction_id="f1240539796",
        title="ニンテンドー3DS コスモブラック",
        current_price=24000,
        bid_count=7,
        start_time=datetime(2026, 8, 12, 12, 40, 31, tzinfo=UTC),
        end_time=datetime(2026, 8, 13, 13, 40, 31, tzinfo=UTC),
        buy_now_price=29000,
        quantity=1,
        is_store=False,
        is_closed=False,
        has_winner=False,
        new_bid=False,
        observed_at=datetime(2026, 8, 13, 13, 0, 0, tzinfo=UTC),
    )
    defaults.update(overrides)
    return AuctionState(**defaults)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def utc(y: int, m: int, d: int, hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(y, m, d, hour, minute, second, tzinfo=UTC)
