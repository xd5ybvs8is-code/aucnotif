import json

import pytest

from app.providers.yahoo.extractor import PageDataExtractionError, PageDataExtractor
from tests.conftest import load_fixture, make_html


def test_extract_from_full_html():
    html = load_fixture("active_auction.html")
    data = PageDataExtractor().extract(html)
    assert data["items"]["productID"] == "f1240539796"
    assert data["items"]["price"] == "24000"
    assert data["navigation"]["pageName"] == "PRODUCT"


def test_extract_from_generated_html():
    data = PageDataExtractor().extract(make_html())
    assert data["items"]["productID"] == "f1240539796"


def test_extract_nested_braces_in_strings():
    items = {
        "productID": "x1",
        "productName": '{"nested": "object"} in title',
        "price": "100",
    }
    data = PageDataExtractor().extract(make_html(items))
    assert data["items"]["productName"] == '{"nested": "object"} in title'


def test_extract_ignores_other_variables():
    html = (
        "<script>var unrelated = {a: 1};</script>"
        + make_html()
        + "<script>var pageData2 = {b: 2};</script>"
    )
    data = PageDataExtractor().extract(html)
    assert data["items"]["productID"] == "f1240539796"


def test_extract_with_escaped_quotes():
    items = {"productID": "x1", "productName": 'with "quotes" and \\ backslash', "price": "100"}
    data = PageDataExtractor().extract(make_html(items))
    assert data["items"]["productName"] == 'with "quotes" and \\ backslash'


def test_extract_missing_pagedata_raises():
    with pytest.raises(PageDataExtractionError):
        PageDataExtractor().extract("<html><body>no data</body></html>")


def test_extract_truncated_pagedata_raises():
    with pytest.raises(PageDataExtractionError):
        PageDataExtractor().extract(load_fixture("truncated_pagedata.html"))


def test_extract_malformed_json_raises():
    html = "<script>var pageData = {items: {productID: 'x1'},};</script>"
    with pytest.raises(PageDataExtractionError):
        PageDataExtractor().extract(html)


def test_extract_result_is_dict():
    data = PageDataExtractor().extract(make_html())
    assert isinstance(data, dict)
    # JSON-совместимость: данные пришли из json.loads
    json.dumps(data)
