"""Tests for yad2_search error surfacing — a blocked scrape must not look like an empty market."""

from pathlib import Path

import pytest

from app.tools import yad2_search
from app.tools.yad2_search import Yad2SearchTool, _apply_price_cap, _build_search_url


async def _run_with_scrape_result(monkeypatch, scrape_result):
    async def fake_scrape(city_code, max_price, min_rooms, max_rooms, limit):
        return scrape_result

    monkeypatch.setattr("app.tools.yad2_search._scrape_yad2", fake_scrape)
    return await Yad2SearchTool().execute(city="haifa", max_price=5500, min_rooms=3, max_rooms=4)


@pytest.mark.asyncio
async def test_bot_verification_page_is_a_loud_error(monkeypatch):
    result = await _run_with_scrape_result(
        monkeypatch,
        {"error": "no __NEXT_DATA__", "title": "Radware Page", "body": "Verifying your browser before proceeding..."},
    )
    assert result.success is False
    assert "bot-verification" in (result.error or "")


@pytest.mark.asyncio
async def test_missing_feed_is_a_loud_error(monkeypatch):
    result = await _run_with_scrape_result(monkeypatch, {"error": "no feed", "title": "Yad2"})
    assert result.success is False
    assert "no feed" in (result.error or "")


@pytest.mark.asyncio
async def test_zero_extracted_from_live_page_is_a_loud_error(monkeypatch):
    result = await _run_with_scrape_result(
        monkeypatch,
        {
            "error": "extracted 0 listings from a live page",
            "title": "דירות להשכרה",
            "page_props_keys": "feed,dehydratedState",
        },
    )
    assert result.success is False
    assert "NOT confirmation of an empty market" in (result.error or "")


@pytest.mark.asyncio
async def test_genuinely_empty_feed_still_reports_no_listings(monkeypatch):
    result = await _run_with_scrape_result(monkeypatch, {"items": [], "count": 0})
    assert result.success is True
    assert "No listings found" in (result.output or "")


@pytest.mark.asyncio
async def test_items_are_returned(monkeypatch):
    result = await _run_with_scrape_result(monkeypatch, {"items": [{"listing_id": "x1", "price": 5000}], "count": 1})
    assert result.success is True
    assert "x1" in (result.output or "")
    assert result.metadata["count"] == 1


@pytest.mark.asyncio
async def test_unknown_city_lists_supported_cities():
    result = await Yad2SearchTool().execute(city="nesher")
    assert result.success is False
    assert "Unknown city" in (result.error or "")


@pytest.mark.asyncio
async def test_bot_challenge_error_is_surfaced_without_radware_page_title(monkeypatch):
    """The interstitial is detected by its fingerprint script, not only by its title text."""
    result = await _run_with_scrape_result(monkeypatch, {"error": "bot_challenge", "title": "", "body": ""})
    assert result.success is False
    assert "NOT an empty market" in (result.error or "")
    assert "YAD2_PROXY_SERVER" in (result.error or "")


def _tool_code() -> str:
    """The tool's source with whole-line comments dropped.

    The comments deliberately name the anti-patterns below to explain why they are banned, so
    matching against raw source would flag the documentation instead of a regression.
    """
    lines = Path(yad2_search.__file__).read_text().splitlines()
    return "\n".join(ln for ln in lines if not ln.lstrip().startswith("#"))


def test_scrape_uses_patchright_not_stock_playwright():
    """Stock Playwright leaks Runtime.enable over CDP and is rejected by Radware every time.

    Reverting this import silently restores a 100%-blocked tool, so pin it here.
    """
    code = _tool_code()
    assert "from patchright.async_api import async_playwright" in code
    assert "from playwright.async_api" not in code


def test_scrape_does_not_reuse_browser_state():
    """A persisted storage_state/user-data-dir downgrades the verdict to a ShieldSquare captcha."""
    code = _tool_code()
    assert "storage_state" not in code
    assert "launch_persistent_context" not in code


def test_scrape_injects_no_stealth_patches():
    """patchright already normalises navigator.webdriver; hand-rolled patches are themselves tells."""
    code = _tool_code()
    assert "add_init_script" not in code
    assert "AutomationControlled" not in code


def test_search_url_omits_robots_disallowed_price_param():
    """Yad2's robots.txt disallows /*?*price= for every user agent; city/rooms are sanctioned."""
    url = _build_search_url("5000", 3, 4)
    assert url == "https://www.yad2.co.il/realestate/rent?city=5000&rooms=3-4"
    assert "price=" not in url


def test_search_url_without_room_bounds_is_city_only():
    assert _build_search_url("4000", None, None) == "https://www.yad2.co.il/realestate/rent?city=4000"


def test_price_cap_drops_over_budget_and_keeps_unpriced():
    items = [
        {"listing_id": "cheap", "price": 4000},
        {"listing_id": "over", "price": 12000},
        {"listing_id": "unpriced", "price": 0},
    ]
    kept = [i["listing_id"] for i in _apply_price_cap(items, 9000, 10)]
    assert kept == ["cheap", "unpriced"]


def test_price_cap_truncates_to_limit():
    items = [{"listing_id": str(n), "price": 1000} for n in range(10)]
    assert len(_apply_price_cap(items, 9000, 3)) == 3


def test_price_cap_without_max_price_only_truncates():
    items = [{"listing_id": "a", "price": 99999}, {"listing_id": "b", "price": 1}]
    assert [i["listing_id"] for i in _apply_price_cap(items, None, 5)] == ["a", "b"]
