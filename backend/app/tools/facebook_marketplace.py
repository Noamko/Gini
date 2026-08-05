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
import time
from datetime import UTC, datetime
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

_NO_SESSION_ERROR = (
    "No valid Facebook session. Bind a 'facebook_session' credential containing at "
    "least the c_user and xs cookies from a logged-in facebook.com browser."
)

_LOGIN_WALL_ERROR = (
    "Facebook served a login wall — the session cookies are expired or insufficient for this "
    "surface. Refresh the facebook_session credential with the FULL cookie header from a "
    "logged-in facebook.com browser (c_user, xs, datr, sb, fr — group pages reject bare "
    "c_user/xs sessions)."
)


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


# Cities that have no Marketplace vanity slug. Facebook silently redirects an unknown
# slug to the generic category feed (location and price filters dropped), so these must
# use the numeric location id instead — found in the city breadcrumb link of any listing
# in that city (/marketplace/<id>/).
_CITY_LOCATION_IDS = {
    "haifa": "110619208966868",
}


def _location_path_segment(location: str) -> str:
    """Resolve a location argument to the /marketplace/<segment>/ path piece."""
    if location.isdigit():
        return location
    slug = _slugify_location(location)
    return _CITY_LOCATION_IDS.get(slug, slug)


def _group_segment(group: str) -> str | None:
    """Resolve a group argument (numeric id, vanity slug, or full URL) to its /groups/<segment>."""
    m = re.search(r"facebook\.com/groups/([^/?#]+)", group)
    if m:
        return m.group(1)
    g = group.strip().strip("/")
    if g and re.fullmatch(r"[A-Za-z0-9._-]+", g):
        return g
    return None


def _walk_json(node, fn, depth: int = 0) -> None:
    """Depth-first, in-order walk over a parsed JSON tree, calling ``fn`` on every dict."""
    if depth > 60:
        return
    if isinstance(node, list):
        for v in node:
            _walk_json(v, fn, depth + 1)
    elif isinstance(node, dict):
        fn(node)
        for v in node.values():
            _walk_json(v, fn, depth + 1)


def _first_in_json(node, getter):
    """First non-None ``getter(dict)`` result in walk order, or None."""
    found: list = []

    def check(obj: dict) -> None:
        if not found:
            value = getter(obj)
            if value is not None:
                found.append(value)

    _walk_json(node, check)
    return found[0] if found else None


def _story_fields(node: dict) -> dict:
    """Extract post fields from a GraphQL story object (one with post_id + comet_sections).

    The message text is the first "text" that sits next to a "ranges" key (that pair is
    the rich-text message shape); comment texts deeper in the subtree lose to it in walk
    order. Same field logic as the JS-side extractor in _GROUP_FEED_EMBED_JS.
    """

    def message_text(o: dict):
        return o["text"] if isinstance(o.get("text"), str) and "ranges" in o else None

    def actor_name(o: dict):
        return o["name"] if o.get("name") and (o.get("__typename") == "User" or o.get("__isActor")) else None

    def image_uri(o: dict):
        return o["image"].get("uri") if isinstance(o.get("image"), dict) else None

    return {
        "post_id": node.get("post_id"),
        "text": _first_in_json(node, message_text),
        "url": _first_in_json(node, lambda o: o.get("wwwURL")),
        "created_at": _first_in_json(node, lambda o: o.get("creation_time")),
        "author": _first_in_json(node, actor_name),
        "image_url": _first_in_json(node, image_uri),
    }


def _harvest_stories(payload, stories: list[dict]) -> None:
    """Collect story objects from a parsed GraphQL payload into ``stories``."""

    def check(obj: dict) -> None:
        if obj.get("post_id") and "comet_sections" in obj:
            stories.append(_story_fields(obj))

    _walk_json(payload, check)


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


async def _run_browser_pages(pages_spec: list[dict], cookies: list[dict]) -> list:
    """Launch stealth Chromium once and run an extractor on each page spec in order.

    Each spec: {"url", "extractor", "arg", "scroll" (wheel rounds), "require_login" (fail
    if the page rendered its logged-out shell), "capture" (collect response bodies whose
    URL contains this substring into the result's __captured__ — e.g. GraphQL feed pages
    loaded while scrolling)}. Stops early on a login wall and appends the marker result
    so callers can surface the expired-session error.
    """
    from playwright.async_api import async_playwright

    results: list = []
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

            captured: dict = {"substr": None, "bodies": []}

            async def _on_response(resp):
                if not captured["substr"] or captured["substr"] not in resp.url:
                    return
                try:
                    captured["bodies"].append(await resp.text())
                except Exception:  # noqa: BLE001 — a response that can't be read is just skipped
                    return

            page.on("response", _on_response)
            for spec in pages_spec:
                captured["substr"] = spec.get("capture")
                captured["bodies"] = []
                await page.goto(spec["url"], wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_timeout(4000)

                # A logged-out session redirects to a login wall — detect it early.
                if "/login" in page.url or "login.php" in page.url:
                    results.append({"__login_required__": True})
                    break

                # Some surfaces (groups) render a logged-out shell at the same URL instead
                # of redirecting: a login form on the page means the session wasn't applied.
                if spec.get("require_login"):
                    logged_out = await page.evaluate(
                        '() => !!document.querySelector(\'input[name="pass"], form[action*="login"]\')'
                    )
                    if logged_out:
                        results.append({"__login_required__": True})
                        break

                for _ in range(spec.get("scroll", 0)):
                    await page.mouse.wheel(0, 3000)
                    await page.wait_for_timeout(1500)

                # Let in-flight captured responses from the last scroll land.
                if spec.get("capture"):
                    await page.wait_for_timeout(2000)

                result = await page.evaluate(spec["extractor"], spec.get("arg"))
                if isinstance(result, dict):
                    result["__final_url__"] = page.url
                    if spec.get("capture"):
                        result["__captured__"] = captured["bodies"]
                results.append(result)
        finally:
            await browser.close()
    return results


async def _run_browser(url: str, cookies: list[dict], extractor, extractor_arg, scroll: bool):
    """Launch stealth Chromium with the session cookies, load ``url``, run ``extractor``."""
    results = await _run_browser_pages(
        [{"url": url, "extractor": extractor, "arg": extractor_arg, "scroll": 3 if scroll else 0}],
        cookies,
    )
    return results[0] if results else None


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
                    "City to search, e.g. 'tel aviv' or 'seattle', or a numeric Marketplace "
                    "location id for cities without a vanity slug. Optional — if omitted, "
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
            return ToolResult(success=False, error=_NO_SESSION_ERROR)

        is_rentals = category == "property_rentals"
        if not query and not is_rentals:
            return ToolResult(success=False, error="A 'query' is required for a general search (category='all').")

        limit = min(max(limit, 1), 30)

        base = "https://www.facebook.com/marketplace"
        slug = _location_path_segment(location) if location else None
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
            return ToolResult(success=False, error=_LOGIN_WALL_ERROR)

        final_url = result.pop("__final_url__", "") if isinstance(result, dict) else ""
        if slug and final_url and f"/marketplace/{slug}/" not in final_url:
            return ToolResult(
                success=False,
                error=(
                    f"Facebook does not recognize the Marketplace location '{location}' — it redirected to "
                    f"the generic feed ({final_url}), which ignores the location and price filters. "
                    "Pass the city's numeric Marketplace location id instead (the /marketplace/<id>/ link "
                    "in the city breadcrumb of any listing in that city)."
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


# JS to pull the full detail of a single listing item page. Primary source is the
# GraphQL data Facebook embeds as <script type="application/json"> blobs: the target
# item's fragments all carry its id, and their structured fields (title, price,
# redacted_description, photos, reverse-geocoded city) are far more reliable than
# guessing from visible text — which used to yield nav links ("Free Stuff") as the
# price and report-listing boilerplate as the description. DOM scraping remains only
# as a fallback in case Facebook reshapes the payload.
_ITEM_JS = r"""(itemId) => {
    const merged = {};
    const visit = (o) => {
        if (!o || typeof o !== 'object') return;
        if (Array.isArray(o)) { for (const v of o) visit(v); return; }
        if (o.id === itemId) {
            for (const [k, v] of Object.entries(o)) if (!(k in merged)) merged[k] = v;
        }
        for (const v of Object.values(o)) visit(v);
    };
    for (const s of document.querySelectorAll('script[type="application/json"]')) {
        const t = s.textContent || '';
        if (!t.includes(itemId)) continue;
        try { visit(JSON.parse(t)); } catch (e) {}
    }

    let title = merged.marketplace_listing_title || '';
    const description = ((merged.redacted_description || {}).text) || '';
    let price = ((merged.formatted_price || {}).text) || '';
    if (!price && merged.listing_price && merged.listing_price.amount) {
        price = merged.listing_price.amount + ' ' + (merged.listing_price.currency || '');
    }
    let location = '';
    const geo = ((merged.location || {}).reverse_geocode) || {};
    if (geo.city_page && geo.city_page.display_name) location = geo.city_page.display_name;
    else if (geo.city) location = geo.city;

    let images = [];
    for (const p of (merged.listing_photos || [])) {
        const uri = (((p || {}).image || {}).uri) || ((p || {}).photo_image_url) || '';
        if (uri) images.push(uri);
    }

    if (!title) {
        title = (document.querySelector('h1') || {}).innerText
            || (document.title || '').replace(/ \| Facebook.*/, '');
    }
    if (!price) {
        const lines = (document.body.innerText || '').split('\n').map(s => s.trim()).filter(Boolean);
        // A real price is a currency symbol followed by digits — a bare "free" would
        // match the "Free Stuff" nav link.
        for (const line of lines) {
            if (/[$£€₪]\s?\d/.test(line) && line.length < 20) { price = line; break; }
        }
    }
    if (!images.length) {
        images = Array.from(document.querySelectorAll('img'))
            .map(i => i.getAttribute('src') || '')
            .filter(s => s.includes('scontent') && s.includes('fbcdn'))
            .filter((v, i, a) => a.indexOf(v) === i);
    }

    return { title: (title || '').trim(), price, images: images.slice(0, 8), description, location };
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
            return ToolResult(success=False, error=_NO_SESSION_ERROR)

        m = re.search(r"(\d{5,})", listing)
        if not m:
            return ToolResult(success=False, error=f"Could not extract a listing id from: {listing}")
        item_id = m.group(1)
        url = f"https://www.facebook.com/marketplace/item/{item_id}/"

        try:
            await logger.ainfo("fb_marketplace_listing_start", item_id=item_id)
            result = await _run_browser(url, cookies, _ITEM_JS, item_id, scroll=False)
        except Exception as e:
            await logger.aerror("fb_marketplace_listing_error", error=str(e))
            return ToolResult(success=False, error=f"Facebook Marketplace listing fetch failed: {str(e)[:200]}")

        if isinstance(result, dict) and result.get("__login_required__"):
            return ToolResult(success=False, error=_LOGIN_WALL_ERROR)

        data = result if isinstance(result, dict) else {}
        data.pop("__final_url__", None)
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


# JS to harvest the account's joined groups from /groups/joins/. Group cards link to
# /groups/<id-or-slug>/; nav chrome uses reserved segments (feed, discover, ...) which
# are skipped. The longest single-line anchor text seen for a segment wins as the name
# (image anchors have no text, "Last active" subtitles are separate lines).
_GROUPS_LIST_JS = r"""() => {
    const skip = new Set(['feed', 'discover', 'joins', 'create', 'search', 'notifications', 'category', 'browse']);
    // Button labels and notification-card text that must never win as the group name.
    const junk = /^(view group|see all|visit|join)$|welcome to|now you can post|^unread/i;
    const seen = new Map();
    for (const a of document.querySelectorAll('a[href*="/groups/"]')) {
        const href = a.getAttribute('href') || '';
        const m = href.match(/(?:https?:\/\/[^/]*facebook\.com)?\/groups\/([^/?#]+)/);
        if (!m || skip.has(m[1])) continue;
        const seg = m[1];
        if (!seen.has(seg)) {
            seen.set(seg, { group_id: seg, name: '', url: 'https://www.facebook.com/groups/' + seg + '/' });
        }
        const entry = seen.get(seg);
        const name = (a.innerText || '').trim().split('\n')[0].trim();
        if (name && !junk.test(name) && name.length < 120 && name.length > entry.name.length) {
            entry.name = name;
        }
    }
    const groups = Array.from(seen.values()).filter(g => g.name);
    return { groups, count: groups.length };
}"""


# The reliable source for group feed posts is Facebook's GraphQL payload, not the
# rendered DOM: permalink hrefs only materialize on hover, and post text sits behind
# "See more" truncation. Story objects (post_id + comet_sections) carry the message
# text, permalink, creation time, author, and photos in their subtree. The first posts
# are embedded as <script type="application/json"> blobs (this extractor); posts loaded
# while scrolling arrive as /api/graphql responses captured by the runner and harvested
# by the matching Python-side walker below.
_GROUP_FEED_EMBED_JS = r"""() => {
    const stories = [];
    const visit = (o, fn, depth) => {
        if (!o || typeof o !== 'object' || depth > 60) return;
        if (Array.isArray(o)) { for (const v of o) visit(v, fn, depth + 1); return; }
        fn(o);
        for (const v of Object.values(o)) visit(v, fn, depth + 1);
    };
    const first = (node, get) => {
        let found = null;
        visit(node, (o) => {
            if (found === null) { const r = get(o); if (r !== undefined && r !== null) found = r; }
        }, 0);
        return found;
    };
    const extract = (node) => ({
        post_id: node.post_id,
        text: first(node, (o) => (typeof o.text === 'string' && 'ranges' in o) ? o.text : null),
        url: first(node, (o) => o.wwwURL),
        created_at: first(node, (o) => o.creation_time),
        author: first(node, (o) => (o.name && (o.__typename === 'User' || o.__isActor)) ? o.name : null),
        image_url: first(node, (o) => (o.image && typeof o.image === 'object') ? o.image.uri : null),
    });
    for (const s of document.querySelectorAll('script[type="application/json"]')) {
        const t = s.textContent || '';
        if (!t.includes('post_id')) continue;
        let data;
        try { data = JSON.parse(t); } catch (e) { continue; }
        visit(data, (o) => { if (o.post_id && o.comet_sections) stories.push(extract(o)); }, 0);
    }
    return { stories };
}"""


class FacebookGroupListTool(BaseTool):
    name = "facebook_group_list"
    description = (
        "List the Facebook groups the operator's account has joined (name, group id, URL), "
        "optionally filtered by a name keyword. Use it to discover which groups to scan with "
        "facebook_group_posts. Requires a Facebook session credential; read-only."
    )
    default_catalog = False
    credential_slots = [_FB_SESSION_SLOT]
    parameters_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Case-insensitive substring to filter group names, e.g. 'tel aviv' or 'דירות'.",
            },
            "limit": {"type": "integer", "description": "Max groups to return (default 50).", "default": 50},
        },
        "required": [],
    }

    async def execute(
        self,
        query: str | None = None,
        limit: int = 50,
        credential_values: dict | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        cookies = _session_cookies(credential_values)
        if not cookies or not any(c["name"] == "c_user" for c in cookies):
            return ToolResult(success=False, error=_NO_SESSION_ERROR)

        limit = min(max(limit, 1), 200)
        url = "https://www.facebook.com/groups/joins/"
        try:
            await logger.ainfo("fb_group_list_start", query=query)
            results = await _run_browser_pages(
                [{"url": url, "extractor": _GROUPS_LIST_JS, "scroll": 6, "require_login": True}], cookies
            )
        except Exception as e:
            await logger.aerror("fb_group_list_error", error=str(e))
            return ToolResult(success=False, error=f"Facebook group list failed: {str(e)[:200]}")

        result = results[0] if results else None
        if isinstance(result, dict) and result.get("__login_required__"):
            return ToolResult(success=False, error=_LOGIN_WALL_ERROR)

        groups = (result or {}).get("groups", []) if isinstance(result, dict) else []
        if query:
            q = query.lower()
            groups = [g for g in groups if q in (g.get("name") or "").lower()]
        groups = groups[:limit]
        await logger.ainfo("fb_group_list_done", count=len(groups))
        if not groups:
            return ToolResult(
                output="No joined groups found" + (f" matching '{query}'." if query else "."),
                metadata={"count": 0},
            )
        return ToolResult(
            output=json.dumps(groups, ensure_ascii=False, indent=2),
            metadata={"count": len(groups)},
        )


class FacebookGroupPostsTool(BaseTool):
    name = "facebook_group_posts"
    description = (
        "Fetch the most recent posts (newest first) from one or more Facebook groups the "
        "operator's account has joined — full post text, author, permalink, posted_at timestamp "
        "and age_hours. Groups are given by id, vanity slug, or URL (find them with "
        "facebook_group_list). Requires a Facebook session credential; read-only (never posts "
        "or comments)."
    )
    default_catalog = False
    credential_slots = [_FB_SESSION_SLOT]
    parameters_schema = {
        "type": "object",
        "properties": {
            "groups": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Groups to scan (max 10 per call): numeric id, vanity slug, or full group URL each.",
            },
            "posts_per_group": {
                "type": "integer",
                "description": "Max posts to return per group (default 10, max 25).",
                "default": 10,
            },
        },
        "required": ["groups"],
    }

    async def execute(
        self,
        groups: list[str],
        posts_per_group: int = 10,
        credential_values: dict | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        cookies = _session_cookies(credential_values)
        if not cookies or not any(c["name"] == "c_user" for c in cookies):
            return ToolResult(success=False, error=_NO_SESSION_ERROR)

        if not groups:
            return ToolResult(success=False, error="Provide at least one group id, slug, or URL in 'groups'.")
        if len(groups) > 10:
            return ToolResult(success=False, error="Too many groups — scan at most 10 per call.")

        segments: list[str] = []
        for g in groups:
            seg = _group_segment(g)
            if not seg:
                return ToolResult(success=False, error=f"Could not extract a group id from: {g}")
            segments.append(seg)

        posts_per_group = min(max(posts_per_group, 1), 25)
        specs = [
            {
                # CHRONOLOGICAL = the group's "New posts" ordering.
                "url": f"https://www.facebook.com/groups/{seg}?sorting_setting=CHRONOLOGICAL",
                "extractor": _GROUP_FEED_EMBED_JS,
                "scroll": 4,
                "capture": "/api/graphql",
                "require_login": True,
            }
            for seg in segments
        ]

        try:
            await logger.ainfo("fb_group_posts_start", groups=segments, posts_per_group=posts_per_group)
            results = await _run_browser_pages(specs, cookies)
        except Exception as e:
            await logger.aerror("fb_group_posts_error", error=str(e))
            return ToolResult(success=False, error=f"Facebook group posts fetch failed: {str(e)[:200]}")

        now = time.time()
        output: list[dict] = []
        total = 0
        for seg, result in zip(segments, results, strict=False):
            if not isinstance(result, dict):
                result = {}
            if result.get("__login_required__"):
                return ToolResult(success=False, error=_LOGIN_WALL_ERROR)
            final_url = result.get("__final_url__", "")
            entry: dict = {"group": seg, "url": f"https://www.facebook.com/groups/{seg}/"}
            # A group the account can't see redirects away from /groups/<seg> — flag it
            # instead of silently returning someone else's feed.
            if final_url and f"/groups/{seg}" not in final_url:
                entry["error"] = f"Group not accessible (redirected to {final_url})."
                output.append(entry)
                continue

            # Stories come from two sources: the page-embedded JSON (first posts) and the
            # GraphQL responses captured while scrolling (the rest). GraphQL bodies are
            # newline-separated JSON documents.
            stories: list[dict] = list(result.get("stories") or [])
            for body in result.get("__captured__") or []:
                if "post_id" not in body:
                    continue
                for line in body.splitlines():
                    line = line.strip()
                    if line and "post_id" in line:
                        try:
                            _harvest_stories(json.loads(line), stories)
                        except ValueError:
                            continue

            # The same post often appears in both sources with different completeness —
            # merge field-by-field, first non-empty value wins.
            by_id: dict[str, dict] = {}
            for s in stories:
                pid = s.get("post_id")
                if not pid:
                    continue
                merged = by_id.setdefault(pid, {})
                for k, v in s.items():
                    if merged.get(k) in (None, "") and v not in (None, ""):
                        merged[k] = v

            posts: list[dict] = []
            for pid, s in by_id.items():
                created = s.get("created_at")
                text = (s.get("text") or "").strip()
                posts.append(
                    {
                        "post_id": pid,
                        "post_url": s.get("url") or f"https://www.facebook.com/groups/{seg}/posts/{pid}/",
                        "author": s.get("author") or "",
                        "posted_at": datetime.fromtimestamp(created, tz=UTC).isoformat() if created else None,
                        "age_hours": round((now - created) / 3600, 1) if created else None,
                        "text": text[:800] + "…" if len(text) > 800 else text,
                        "image_url": s.get("image_url") or "",
                    }
                )
            posts.sort(key=lambda p: p["age_hours"] if p["age_hours"] is not None else float("inf"))
            entry["posts"] = posts[:posts_per_group]
            total += len(entry["posts"])
            output.append(entry)

        await logger.ainfo("fb_group_posts_done", groups=len(output), posts=total)
        return ToolResult(
            output=json.dumps(output, ensure_ascii=False, indent=2),
            metadata={"groups": len(output), "posts": total},
        )
