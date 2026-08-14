import pytest

from app.domain.validation import InvalidAuctionUrl, extract_auction_id, validate_auction_url


@pytest.mark.parametrize(
    "url",
    [
        "https://page.auctions.yahoo.co.jp/jp/auction/f1240539796",
        "http://page.auctions.yahoo.co.jp/jp/auction/f1240539796",
        "https://www.page.auctions.yahoo.co.jp/jp/auction/f1240539796",
        "https://page.auctions.yahoo.co.jp/jp/auction/f1240539796?ref=search",
    ],
)
def test_valid_urls(url):
    canonical = validate_auction_url(url)
    assert canonical == "https://page.auctions.yahoo.co.jp/jp/auction/f1240539796"


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.com/jp/auction/f1240539796",
        "https://page.auctions.yahoo.co.jp/jp/auction/../../etc/passwd",
        "https://page.auctions.yahoo.co.jp/sell/jp/show/f1240539796",
        "javascript:alert(1)",
        "",
        "https://page.auctions.yahoo.co.jp/jp/auction/",
        "ftp://page.auctions.yahoo.co.jp/jp/auction/f1240539796",
        "https://page.auctions.yahoo.co.jp/jp/auction/f1240539796\"onclick=\"alert(1)",
    ],
)
def test_invalid_urls(url):
    with pytest.raises(InvalidAuctionUrl):
        validate_auction_url(url)


def test_extract_auction_id():
    assert extract_auction_id("https://page.auctions.yahoo.co.jp/jp/auction/f1240539796") == "f1240539796"


def test_extract_auction_id_invalid():
    with pytest.raises(InvalidAuctionUrl):
        extract_auction_id("https://google.com")
