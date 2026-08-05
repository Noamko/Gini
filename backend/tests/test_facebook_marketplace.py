"""Tests for the Facebook Marketplace tools (session arrives via the ``facebook_session`` slot)."""

import pytest

from app.tools.facebook_marketplace import (
    FacebookGroupListTool,
    FacebookGroupPostsTool,
    FacebookMarketplaceListingTool,
    FacebookMarketplaceSearchTool,
    _group_segment,
    _harvest_stories,
    _location_path_segment,
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


def test_location_path_segment():
    # Cities with a vanity slug pass through slugified.
    assert _location_path_segment("Tel Aviv") == "telaviv"
    # Cities without a vanity slug map to their numeric Marketplace location id.
    assert _location_path_segment("Haifa") == "110619208966868"
    # A numeric location id is used as-is.
    assert _location_path_segment("108140382539956") == "108140382539956"


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


def test_group_segment():
    # Full URLs (with or without trailing path/query) resolve to the path segment.
    assert _group_segment("https://www.facebook.com/groups/123456789/") == "123456789"
    assert _group_segment("https://www.facebook.com/groups/telavivrentals?ref=share") == "telavivrentals"
    # Bare ids and vanity slugs pass through.
    assert _group_segment("123456789") == "123456789"
    assert _group_segment("telaviv.rentals") == "telaviv.rentals"
    # Free-text group names (spaces/Hebrew) don't resolve — the caller must use facebook_group_list.
    assert _group_segment("דירות להשכרה בתל אביב") is None
    assert _group_segment("Tel Aviv Rentals") is None


@pytest.mark.asyncio
async def test_group_tools_without_session_return_error():
    list_result = await FacebookGroupListTool().execute(credential_values={})
    posts_result = await FacebookGroupPostsTool().execute(groups=["123"], credential_values={})
    for result in (list_result, posts_result):
        assert result.success is False
        assert "session" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_group_posts_validates_groups():
    tool = FacebookGroupPostsTool()
    creds = {"facebook_session": "c_user=1; xs=2"}

    result = await tool.execute(groups=[], credential_values=creds)
    assert result.success is False
    assert "at least one" in (result.error or "").lower()

    result = await tool.execute(groups=[str(i) for i in range(11)], credential_values=creds)
    assert result.success is False
    assert "at most 10" in (result.error or "")

    result = await tool.execute(groups=["not a valid group!"], credential_values=creds)
    assert result.success is False
    assert "group id" in (result.error or "").lower()


def test_harvest_stories_extracts_post_fields_from_graphql_payload():
    payload = {
        "data": {
            "node": {
                "post_id": "321",
                "comet_sections": {
                    "content": {
                        "story": {
                            "message": {"text": "דירת 3 חדרים להשכרה", "ranges": []},
                            "wwwURL": "https://www.facebook.com/groups/g/permalink/321/",
                            "creation_time": 1785588165,
                            "actors": [{"__typename": "User", "name": "Jane Doe"}],
                            "attachments": [{"media": {"image": {"uri": "https://scontent.example/img.jpg"}}}],
                        }
                    }
                },
            },
            # An object with post_id but no comet_sections is metadata, not a story.
            "other": {"post_id": "999"},
        }
    }
    stories: list[dict] = []
    _harvest_stories(payload, stories)
    assert len(stories) == 1
    story = stories[0]
    assert story["post_id"] == "321"
    assert story["text"] == "דירת 3 חדרים להשכרה"
    assert story["url"].endswith("/321/")
    assert story["created_at"] == 1785588165
    assert story["author"] == "Jane Doe"
    assert story["image_url"] == "https://scontent.example/img.jpg"


def test_tools_are_optin_and_declare_session_slot():
    for tool in (
        FacebookMarketplaceSearchTool(),
        FacebookMarketplaceListingTool(),
        FacebookGroupListTool(),
        FacebookGroupPostsTool(),
    ):
        assert tool.default_catalog is False
        slots = {s.name: s for s in tool.credential_slots}
        assert "facebook_session" in slots
        assert slots["facebook_session"].type == "facebook_session"
        assert slots["facebook_session"].required is True
