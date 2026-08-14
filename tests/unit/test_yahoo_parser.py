from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.providers.base import PageDataParseError
from app.providers.yahoo.extractor import PageDataExtractor
from app.providers.yahoo.provider import YahooAuctionProvider
from app.schemas.yahoo import PageData, PageDataItems, YahooAuctionData
from tests.conftest import DEFAULT_ITEMS, load_fixture, load_fixture_json, make_html


def _provider():
    return YahooAuctionProvider(http_client=None, extractor=PageDataExtractor())


def test_full_mapping_yahoo_to_auction_state():
    state, _ = _provider().parse_auction_state(make_html(), "https://example.com")
    assert state.auction_id == "f1240539796"
    assert state.current_price == 24000  # price → current_price
    assert state.buy_now_price == 29000  # winPrice → buy_now_price
    assert state.bid_count == 7  # bids → bid_count
    assert state.end_time == datetime(2026, 8, 13, 13, 40, 31, tzinfo=UTC)  # JST→UTC
    assert state.start_time == datetime(2026, 8, 12, 12, 40, 31, tzinfo=UTC)
    assert state.is_store is False
    assert state.is_closed is False
    assert state.has_winner is False
    assert state.new_bid is False
    assert state.quantity == 1
    assert state.title.startswith("ニンテンドー3DS")


def test_win_price_never_treated_as_current_price():
    state, _ = _provider().parse_auction_state(make_html(), "https://example.com")
    assert state.current_price == 24000
    assert state.buy_now_price == 29000
    assert state.current_price != state.buy_now_price


def test_auction_without_bids():
    html = make_html(load_fixture_json("auction_without_bids.json")["items"])
    state, _ = _provider().parse_auction_state(html, "https://example.com")
    assert state.bid_count == 0
    assert state.current_price == 1000
    assert state.buy_now_price is None  # пустой winPrice
    assert state.is_store is True


def test_closed_auction():
    html = make_html(load_fixture_json("closed_auction.json")["items"])
    state, _ = _provider().parse_auction_state(html, "https://example.com")
    assert state.is_closed is True
    assert state.has_winner is True
    assert state.new_bid is True


def test_boolean_and_numeric_strings_coerced():
    items = dict(DEFAULT_ITEMS)
    items.update(
        price="10,500", bids="0", isStore="1", isClosed="0", hasWinner="1", newBid="1"
    )
    data = YahooAuctionData.from_items(PageDataItems.model_validate(items))
    assert data.price == 10500
    assert data.bids == 0
    assert data.is_store is True
    assert data.has_winner is True
    assert data.new_bid is True


def test_missing_product_id_raises():
    items = dict(DEFAULT_ITEMS)
    items["productID"] = ""
    with pytest.raises(PageDataParseError):
        _provider().parse_auction_state(make_html(items), "https://example.com")


def test_invalid_price_raises():
    items = dict(DEFAULT_ITEMS)
    items["price"] = "NOT_A_NUMBER"
    with pytest.raises(PageDataParseError):
        _provider().parse_auction_state(make_html(items), "https://example.com")


def test_invalid_bids_raises():
    items = dict(DEFAULT_ITEMS)
    items["bids"] = "???"
    with pytest.raises(PageDataParseError):
        _provider().parse_auction_state(make_html(items), "https://example.com")


def test_invalid_endtime_raises():
    items = dict(DEFAULT_ITEMS)
    items["endtime"] = "not-a-date"
    with pytest.raises(PageDataParseError):
        _provider().parse_auction_state(make_html(items), "https://example.com")


def test_invalid_boolean_raises():
    items = dict(DEFAULT_ITEMS)
    items["isClosed"] = "maybe"
    with pytest.raises(PageDataParseError):
        _provider().parse_auction_state(make_html(items), "https://example.com")


def test_malformed_pagedata_fixture_raises():
    html = load_fixture("malformed_pagedata.html")
    with pytest.raises(PageDataParseError):
        _provider().parse_auction_state(html, "https://example.com")


def test_navigation_not_part_of_state():
    items = dict(DEFAULT_ITEMS)
    page_data = PageData.model_validate(
        {"navigation": {"isLogin": 1, "device": "MOBILE"}, "items": items}
    )
    data = YahooAuctionData.from_items(PageDataItems.model_validate(page_data.items))
    assert not hasattr(data, "navigation")
    assert not hasattr(data, "is_login")


def test_missing_items_raises():
    html = make_html()
    html = html.replace('"items"', '"broken"', 1)
    with pytest.raises(PageDataParseError):
        _provider().parse_auction_state(html, "https://example.com")


def test_unknown_fields_ignored():
    items = dict(DEFAULT_ITEMS)
    items["futureField"] = "something"
    state, _ = _provider().parse_auction_state(make_html(items), "https://example.com")
    assert state.auction_id == "f1240539796"


def test_empty_endtime_allowed_as_none():
    items = dict(DEFAULT_ITEMS)
    items["endtime"] = ""
    state, _ = _provider().parse_auction_state(make_html(items), "https://example.com")
    assert state.end_time is None


def test_pydantic_rejects_non_string_product_id():
    with pytest.raises(ValidationError):
        YahooAuctionData.model_validate({"product_id": 123})
