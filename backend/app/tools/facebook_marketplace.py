"""Facebook Marketplace search + listing tools.

Facebook has no public Marketplace API, so these tools drive a stealth headless
Chromium (Playwright) session authenticated with the operator's own Facebook cookies.
The session is supplied through a ``facebook_session`` credential slot: paste the
``c_user`` and ``xs`` cookies (plus any others) from a logged-in facebook.com browser.

Read-only: these tools search and read listings. They never post, message, or mutate
account state.
"""

import json
import re
from typing import Any

import structlog

from app.tools.base import BaseTool, CredentialSlot, ToolResult

logger = structlog.get_logger("facebook_marketplace")

# One slot holds the whole Facebook cookie string. A dedicated type lets a single
# bound credential of this type auto-bind to the slot (grant_resolver single-slot rule).
_FB_SESSION_SLOT = CredentialSlot(
    name="facebook_session",
    type="facebook_session",
    required=True,
    description=(
        "Facebook session cookies from a logged-in facebook.com browser. Paste either the raw "
        "cookie header (e.g. 'c_user=100...; xs=34%3A...; datr=...') or just the c_user and xs pairs."
    ),
)

_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"

# Cookies that actually matter for an authenticated Marketplace session. Anything else
# in the pasted string is ignored.
_KNOWN_FB_COOKIES = {"c_user", "xs", "datr", "sb", "fr", "wd", "presence", "dpr"}


def _parse_cookie_string(raw: str) -> list[dict[str, str]]:
    """Parse a 'k=v; k2=v2' cookie string into Playwright cookie dicts for .facebook.com."""
    cookies: list[dict[str, str]] = []
    for pair in raw.strip().split(";"):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        name, _, value = pair.partition("=")
        name = name.strip()
        value = value.strip()
        if name not in _KNOWN_FB_COOKIES or not value:
            continue
        cookies.append(
            {
                "name": name,
                "value": value,
                "domain": ".facebook.com",
                "path": "/",
                "httpOnly": name in {"xs", "fr"},
                "secure": True,
                "sameSite": "None",
            }
        )
    return cookies


def _session_cookies(credential_values: dict | None) -> list[dict[str, str]]:
    raw = (credential_values or {}).get("facebook_session")
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    if not raw or not isinstance(raw, str):
        return []
    return _parse_cookie_string(raw)


def _slugify_location(location: str) -> str:
    """Turn a city name into the vanity slug Facebook uses in /marketplace/<slug>/search."""
    return re.sub(r"[^a-z0-9]", "", location.lower())


# JS run in the page to harvest Marketplace listing cards from the rendered DOM.
# Facebook obfuscates its GraphQL payloads, so we scrape anchors to /marketplace/item/
# and the price/title/image text rendered inside each card.
_EXTRACT_JS = r"""(limit) => {
    const seen = new Set();
    const items = [];
    const anchors = document.querySelectorAll('a[href*="/marketplace/item/"]');
    for (const a of anchors) {
        if (items.length >= limit) break;
        const m = a.getAttribute('href').match(/\/marketplace\/item\/(\d+)/);
        if (!m) continue;
        const id = m[1];
        if (seen.has(id)) continue;
        seen.add(id);

        const text = (a.innerText || '').split('\n').map(s => s.trim()).filter(Boolean);
        // Badge/label lines Facebook renders on cards that are not the real title.
        const isBadge = (s) => /^(just listed|new|sponsored|featured)$/i.test(s);
        // Price is the line containing a currency symbol or 'Free'.
        let price = '';
        let title = '';
        let location = '';
        for (const line of text) {
            if (!price && (/[$£€₪]|\bfree\b/i.test(line))) { price = line; continue; }
            if (!title && line.length > 3 && !/^[$£€₪]/.test(line) && !isBadge(line)) { title = line; continue; }
        }
        // Last text line is usually the location.
        if (text.length) location = text[text.length - 1];

        const img = a.querySelector('img');
        const image_url = img ? (img.getAttribute('src') || '') : '';

        items.push({
            listing_id: id,
            title: title,
            price: price,
            location: location,
            image_url: image_url,
            listing_url: 'https://www.facebook.com/marketplace/item/' + id + '/',
        });
    }
    return { items, count: items.length, anchors: anchors.length };
}"""


async def _run_browser(url: str, cookies: list[dict], extractor, extractor_arg, scroll: bool):
    """Launch stealth Chromium with the session cookies, load ``url``, run ``extractor``."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        try:
            context = await browser.new_context(
                user_agent=_UA,
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
            )
            if cookies:
                await context.add_cookies(cookies)
            page = await context.new_page()
            await page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});window.chrome = { runtime: {} };"
            )
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(4000)

            # A logged-out session redirects to a login wall — detect it early.
            if "/login" in page.url or "login.php" in page.url:
                return {"__login_required__": True}

            if scroll:
                for _ in range(3):
                    await page.mouse.wheel(0, 3000)
                    await page.wait_for_timeout(1500)

            return await page.evaluate(extractor, extractor_arg)
        finally:
            await browser.close()


class FacebookMarketplaceSearchTool(BaseTool):
    name = "facebook_marketplace_search"
    description = (
        "Search Facebook Marketplace for listings by keyword, or browse the Property Rentals "
        "category for apartments. Returns structured results (title, price, location, image, "
        "listing URL). Requires a Facebook session credential; read-only (does not post or message)."
    )
    default_catalog = False  # opt-in; granted via the Facebook Marketplace skill
    credential_slots = [_FB_SESSION_SLOT]
    parameters_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Search keywords, e.g. 'ikea desk'. Optional when category='property_rentals' "
                    "(the category can be browsed without a keyword); required otherwise."
                ),
            },
            "category": {
                "type": "string",
                "enum": ["all", "property_rentals"],
                "description": (
                    "'all' = general keyword search (default). 'property_rentals' = the apartment "
                    "rentals category, where price filters apply to monthly rent."
                ),
                "default": "all",
            },
            "location": {
                "type": "string",
                "description": (
                    "City to search, e.g. 'tel aviv' or 'seattle'. Optional — if omitted, "
                    "Facebook uses the logged-in account's default Marketplace location."
                ),
            },
            "min_price": {"type": "integer", "description": "Minimum price filter (monthly rent for rentals)."},
            "max_price": {"type": "integer", "description": "Maximum price filter (monthly rent for rentals)."},
            "min_bedrooms": {
                "type": "integer",
                "description": "Minimum bedrooms (property_rentals only). Note: Facebook counts bedrooms, not Israeli 'rooms'.",
            },
            "sort_by": {
                "type": "string",
                "enum": ["best_match", "price_ascend", "price_descend", "distance_ascend", "creation_time_descend"],
                "description": "Result ordering. 'creation_time_descend' = newest first.",
            },
            "days_since_listed": {
                "type": "integer",
                "enum": [1, 7, 30],
                "description": "Only listings posted within this many days.",
            },
            "limit": {
                "type": "integer",
                "description": "Number of results to return (default 10, max 30).",
                "default": 10,
            },
        },
        "required": [],
    }

    async def execute(
        self,
        query: str | None = None,
        category: str = "all",
        location: str | None = None,
        min_price: int | None = None,
        max_price: int | None = None,
        min_bedrooms: int | None = None,
        sort_by: str | None = None,
        days_since_listed: int | None = None,
        limit: int = 10,
        credential_values: dict | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        cookies = _session_cookies(credential_values)
        if not cookies or not any(c["name"] == "c_user" for c in cookies):
            return ToolResult(
                success=False,
                error=(
                    "No valid Facebook session. Bind a 'facebook_session' credential containing at "
                    "least the c_user and xs cookies from a logged-in facebook.com browser."
                ),
            )

        is_rentals = category == "property_rentals"
        if not query and not is_rentals:
            return ToolResult(success=False, error="A 'query' is required for a general search (category='all').")

        limit = min(max(limit, 1), 30)

        base = "https://www.facebook.com/marketplace"
        slug = _slugify_location(location) if location else None
        endpoint = "propertyrentals" if is_rentals else "search"
        # The rentals category needs the /category/ prefix when no location slug is given.
        if slug:
            path = f"{base}/{slug}/{endpoint}"
        elif is_rentals:
            path = f"{base}/category/{endpoint}"
        else:
            path = f"{base}/{endpoint}"

        params: list[str] = []
        if query:
            params.append(f"query={query.replace(' ', '%20')}")
        if min_price is not None:
            params.append(f"minPrice={min_price}")
        if max_price is not None:
            params.append(f"maxPrice={max_price}")
        if is_rentals and min_bedrooms is not None:
            params.append(f"bedrooms={min_bedrooms}")
        if sort_by:
            params.append(f"sortBy={sort_by}")
        if days_since_listed:
            params.append(f"daysSinceListed={days_since_listed}")
        url = f"{path}?{'&'.join(params)}" if params else path

        try:
            await logger.ainfo(
                "fb_marketplace_search_start", query=query, category=category, location=location, url=url
            )
            result = await _run_browser(url, cookies, _EXTRACT_JS, limit, scroll=True)
        except Exception as e:
            await logger.aerror("fb_marketplace_search_error", error=str(e))
            return ToolResult(success=False, error=f"Facebook Marketplace search failed: {str(e)[:200]}")

        if isinstance(result, dict) and result.get("__login_required__"):
            return ToolResult(
                success=False,
                error=(
                    "Facebook redirected to a login wall — the session cookies are expired or invalid. "
                    "Refresh the facebook_session credential with current c_user/xs cookies."
                ),
            )

        items = (result or {}).get("items", []) if isinstance(result, dict) else []
        await logger.ainfo("fb_marketplace_search_done", count=len(items))
        if not items:
            return ToolResult(
                output="No listings found. Facebook may have returned an empty or blocked page.",
                metadata={"count": 0, "url": url},
            )
        return ToolResult(
            output=json.dumps(items[:limit], ensure_ascii=False, indent=2),
            metadata={"count": len(items[:limit]), "url": url},
        )


# JS to pull the full detail of a single listing item page.
_ITEM_JS = r"""() => {
    const bodyText = document.body.innerText || '';
    const lines = bodyText.split('\n').map(s => s.trim()).filter(Boolean);

    let price = '';
    for (const line of lines) {
        if (/[$£€₪]|\bfree\b/i.test(line) && line.length < 20) { price = line; break; }
    }
    const title = (document.querySelector('h1') || {}).innerText
        || (document.title || '').replace(/ \| Facebook.*/, '');

    // Collect distinct listing photos.
    const images = Array.from(document.querySelectorAll('img'))
        .map(i => i.getAttribute('src') || '')
        .filter(s => s.includes('scontent') && s.includes('fbcdn'))
        .filter((v, i, a) => a.indexOf(v) === i)
        .slice(0, 8);

    // Description: the longest text block on the page is usually the listing body.
    let description = '';
    for (const line of lines) {
        if (line.length > description.length && line.length < 5000) description = line;
    }

    return { title: (title || '').trim(), price, images, description };
}"""


class FacebookMarketplaceListingTool(BaseTool):
    name = "facebook_marketplace_listing"
    description = (
        "Fetch the full detail of one Facebook Marketplace listing (title, price, description, "
        "photos) by its item id or URL. Requires a Facebook session credential; read-only."
    )
    default_catalog = False
    credential_slots = [_FB_SESSION_SLOT]
    parameters_schema = {
        "type": "object",
        "properties": {
            "listing": {
                "type": "string",
                "description": "Marketplace item id (e.g. '1234567890') or full listing URL.",
            },
        },
        "required": ["listing"],
    }

    async def execute(
        self,
        listing: str,
        credential_values: dict | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        cookies = _session_cookies(credential_values)
        if not cookies or not any(c["name"] == "c_user" for c in cookies):
            return ToolResult(
                success=False,
                error=(
                    "No valid Facebook session. Bind a 'facebook_session' credential containing at "
                    "least the c_user and xs cookies from a logged-in facebook.com browser."
                ),
            )

        m = re.search(r"(\d{5,})", listing)
        if not m:
            return ToolResult(success=False, error=f"Could not extract a listing id from: {listing}")
        item_id = m.group(1)
        url = f"https://www.facebook.com/marketplace/item/{item_id}/"

        try:
            await logger.ainfo("fb_marketplace_listing_start", item_id=item_id)
            result = await _run_browser(url, cookies, _ITEM_JS, None, scroll=False)
        except Exception as e:
            await logger.aerror("fb_marketplace_listing_error", error=str(e))
            return ToolResult(success=False, error=f"Facebook Marketplace listing fetch failed: {str(e)[:200]}")

        if isinstance(result, dict) and result.get("__login_required__"):
            return ToolResult(
                success=False,
                error=(
                    "Facebook redirected to a login wall — the session cookies are expired or invalid. "
                    "Refresh the facebook_session credential with current c_user/xs cookies."
                ),
            )

        data = result if isinstance(result, dict) else {}
        data["listing_id"] = item_id
        data["listing_url"] = url
        if not data.get("title") and not data.get("images"):
            return ToolResult(
                success=False,
                error="Listing page returned no content — it may be removed, sold, or region-locked.",
                metadata={"url": url},
            )
        return ToolResult(
            output=json.dumps(data, ensure_ascii=False, indent=2),
            metadata={"listing_id": item_id, "url": url},
        )
