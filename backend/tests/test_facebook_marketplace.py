"""Tests for the Facebook Marketplace tools (session arrives via the ``facebook_session`` slot)."""

import pytest

from app.tools.facebook_marketplace import (
    FacebookMarketplaceListingTool,
    FacebookMarketplaceSearchTool,
    _parse_cookie_string,
    _session_cookies,
    _slugify_location,
)


def test_parse_cookie_string_keeps_known_and_drops_junk():
    cookies = _parse_cookie_string("c_user=100055; xs=34%3Aabc%3A2; datr=xyz; junk=1; =empty")
    names = {c["name"] for c in cookies}
    assert names == {"c_user", "xs", "datr"}
    xs = next(c for c in cookies if c["name"] == "xs")
    assert xs["value"] == "34%3Aabc%3A2"
    assert xs["domain"] == ".facebook.com"
    assert xs["httpOnly"] is True


def test_session_cookies_unwraps_multi_value_and_handles_missing():
    assert _session_cookies(None) == []
    assert _session_cookies({}) == []
    # A multi-slot binding arrives as a list; the first value is used.
    cookies = _session_cookies({"facebook_session": ["c_user=1; xs=2"]})
    assert {c["name"] for c in cookies} == {"c_user", "xs"}


def test_slugify_location():
    assert _slugify_location("New York") == "newyork"
    assert _slugify_location("San Francisco!") == "sanfrancisco"


@pytest.mark.asyncio
async def test_search_without_session_returns_error():
    tool = FacebookMarketplaceSearchTool()
    result = await tool.execute(query="ikea desk", credential_values={})
    assert result.success is False
    assert "session" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_general_search_requires_query():
    tool = FacebookMarketplaceSearchTool()
    result = await tool.execute(
        category="all",
        credential_values={"facebook_session": "c_user=1; xs=2"},
    )
    assert result.success is False
    assert "query" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_search_rejects_session_without_c_user():
    tool = FacebookMarketplaceSearchTool()
    result = await tool.execute(
        query="ikea desk",
        credential_values={"facebook_session": "datr=xyz; sb=abc"},
    )
    assert result.success is False
    assert "c_user" in (result.error or "")


@pytest.mark.asyncio
async def test_listing_requires_valid_id():
    tool = FacebookMarketplaceListingTool()
    result = await tool.execute(
        listing="not-an-id",
        credential_values={"facebook_session": "c_user=1; xs=2"},
    )
    assert result.success is False
    assert "listing id" in (result.error or "").lower()


def test_tools_are_optin_and_declare_session_slot():
    for tool in (FacebookMarketplaceSearchTool(), FacebookMarketplaceListingTool()):
        assert tool.default_catalog is False
        slots = {s.name: s for s in tool.credential_slots}
        assert "facebook_session" in slots
        assert slots["facebook_session"].type == "facebook_session"
        assert slots["facebook_session"].required is True
