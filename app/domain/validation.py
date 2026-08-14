import re

YAHOO_AUCTION_URL_RE = re.compile(
    r"^https?://(?:www\.)?page\.auctions\.yahoo\.co\.jp/jp/auction/([a-zA-Z0-9]+)/?(?:\?.*)?$"
)


class InvalidAuctionUrl(ValueError):
    pass


def validate_auction_url(url: str) -> str:
    """Валидирует URL Yahoo Auctions и возвращает каноническую форму.

    Разрешены только https/http URL страниц аукционов Yahoo Auctions Japan.
    """
    url = url.strip()
    if len(url) > 2048:
        raise InvalidAuctionUrl("URL is too long")
    match = YAHOO_AUCTION_URL_RE.match(url)
    if not match:
        raise InvalidAuctionUrl(
            "Допустимы только ссылки вида https://page.auctions.yahoo.co.jp/jp/auction/XXXX"
        )
    auction_id = match.group(1)
    return f"https://page.auctions.yahoo.co.jp/jp/auction/{auction_id}"


def extract_auction_id(url: str) -> str:
    match = YAHOO_AUCTION_URL_RE.match(url.strip())
    if not match:
        raise InvalidAuctionUrl("Not a Yahoo auction URL")
    return match.group(1)
