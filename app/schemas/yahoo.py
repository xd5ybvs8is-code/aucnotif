from datetime import datetime

from pydantic import BaseModel, field_validator

from app.domain.time import parse_yahoo_datetime


def _to_int(v: str | int | None) -> int | None:
    if v is None:
        return None
    if isinstance(v, int):
        return v
    text = v.strip().replace(",", "")
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        raise ValueError(f"Cannot parse integer from {v!r}") from None


def _to_bool(v: str | int | bool | None) -> bool | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, int):
        return v != 0
    text = v.strip().lower()
    if text in ("1", "true", "yes"):
        return True
    if text in ("0", "false", "no", ""):
        return False
    raise ValueError(f"Cannot parse boolean from {v!r}")


class PageDataItems(BaseModel):
    """Сырые поля pageData.items — все значения у Yahoo строковые."""

    model_config = {"extra": "ignore", "str_strip_whitespace": True}

    productID: str | None = None
    productName: str | None = None
    productCategoryID: str | None = None
    price: str | None = None
    starttime: str | None = None
    endtime: str | None = None
    winPrice: str | None = None
    quantity: str | None = None
    bids: str | None = None
    isStore: str | None = None
    isAdult: str | None = None
    isClosed: str | None = None
    hasWinner: str | None = None
    newBid: str | None = None
    enableBooth: str | None = None
    catid1: str | None = None
    catid2: str | None = None
    catid3: str | None = None
    catid4: str | None = None
    catid5: str | None = None
    catid6: str | None = None


class PageData(BaseModel):
    model_config = {"extra": "ignore"}

    navigation: dict | None = None
    items: PageDataItems | None = None


class YahooAuctionData(BaseModel):
    """Провалидированные данные аукциона, всё ещё в терминах Yahoo."""

    product_id: str
    product_name: str | None = None
    price: int | None = None
    starttime: datetime | None = None
    endtime: datetime | None = None
    win_price: int | None = None
    quantity: int | None = None
    bids: int | None = None
    is_store: bool | None = None
    is_closed: bool | None = None
    has_winner: bool | None = None
    new_bid: bool | None = None

    @field_validator("price", "win_price", "quantity", "bids", mode="before")
    @classmethod
    def _ints(cls, v):
        return _to_int(v)

    @field_validator("is_store", "is_closed", "has_winner", "new_bid", mode="before")
    @classmethod
    def _bools(cls, v):
        return _to_bool(v)

    @field_validator("starttime", "endtime", mode="before")
    @classmethod
    def _datetimes(cls, v):
        if v is None or v == "":
            return None
        return parse_yahoo_datetime(str(v))

    @classmethod
    def from_items(cls, items: PageDataItems) -> "YahooAuctionData":
        if not items.productID:
            raise ValueError("pageData.items.productID is empty")
        return cls(
            product_id=items.productID,
            product_name=items.productName,
            price=items.price,
            starttime=items.starttime,
            endtime=items.endtime,
            win_price=items.winPrice,
            quantity=items.quantity,
            bids=items.bids,
            is_store=items.isStore,
            is_closed=items.isClosed,
            has_winner=items.hasWinner,
            new_bid=items.newBid,
        )
