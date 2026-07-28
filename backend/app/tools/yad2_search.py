"""Yad2 apartment search tool — uses patchright to scrape listings past Radware bot detection."""
import json
import os
from typing import Any

import structlog

from app.tools.base import BaseTool, ToolResult

logger = structlog.get_logger("yad2_search")

# City codes for common Israeli cities
CITY_CODES = {
    "tel aviv": "5000", "jerusalem": "3000", "haifa": "4000",
    "petah tikva": "7900", "rishon lezion": "8300", "ashdod": "70",
    "netanya": "7400", "beer sheva": "9000", "bnei brak": "6100",
    "holon": "6600", "ramat gan": "8600", "herzliya": "6400",
    "kfar saba": "6900", "ra'anana": "8700", "bat yam": "6200",
    "modi'in": "1200", "rehovot": "8400", "ashkelon": "2800",
    "nahariya": "7300", "acre": "4100", "eilat": "2600",
}

# Yad2 sits behind Radware Bot Manager. Stock Playwright is rejected outright — not because of
# the source IP, but because its CDP session calls Runtime.enable, which leaks a detectable
# execution-context signal into every page. patchright is a drop-in Playwright fork that keeps
# that channel quiet, and it clears the challenge from this host on a plain headless launch.
#
# Two things that look like hardening actively make the verdict worse and must stay out:
# reusing a persisted storage_state/user-data-dir (it earns a ShieldSquare captcha rather than
# the feed), and injecting stealth init scripts or --disable-blink-features flags (patchright
# already normalises navigator.webdriver, and the patches themselves are fingerprintable).

# A residential proxy is no longer needed, but keep the knob for hosts whose IP is blacklisted
# outright. Inert when unset.
_PROXY_SERVER = os.environ.get("YAD2_PROXY_SERVER", "")
_PROXY_USERNAME = os.environ.get("YAD2_PROXY_USERNAME", "")
_PROXY_PASSWORD = os.environ.get("YAD2_PROXY_PASSWORD", "")

# Listings historically lived in pageProps.feed; newer pages keep them in React Query's
# dehydratedState. Walk feed → dehydratedState → all of pageProps, then fall back to DOM
# links. Extracting 0 items from a live page is an error unless the page explicitly shows
# Yad2's empty-state text — parser drift must never look like an empty market.
_EXTRACT_JS = """(limit) => {
    try {
        const el = document.getElementById('__NEXT_DATA__');
        if (!el) return {error: 'no __NEXT_DATA__', title: document.title,
                         body: (document.body?.innerText || '').slice(0, 200)};
        const d = JSON.parse(el.textContent);
        const pp = d.props?.pageProps;
        if (!pp) return {error: 'no pageProps', title: document.title};

        const seen = new Set();
        const items = [];
        const parsePrice = (v) => {
            if (typeof v === 'number') return v;
            if (typeof v === 'string') { const digits = v.replace(/[^0-9]/g, ''); return digits ? parseInt(digits, 10) : 0; }
            return 0;
        };
        function looksLikeListing(o) {
            return o && typeof o === 'object' && !Array.isArray(o) &&
                (o.address || o.token || o.adNumber || o.title_1) &&
                (o.price !== undefined || o.address);
        }
        function push(item) {
            const addr = item.address || {};
            const listingId = String(item.token || item.id || item.adNumber || '');
            if (listingId) {
                if (seen.has(listingId)) return;
                seen.add(listingId);
            }
            let rawImgs = item.images || item.media?.pics || item.metaData?.images || [];
            if (!Array.isArray(rawImgs)) rawImgs = [];
            if (!rawImgs.length && item.metaData?.coverImage) rawImgs = [item.metaData.coverImage];
            const images = rawImgs.map(img => {
                if (typeof img === 'string') return img;
                if (img?.src) return img.src;
                if (img?.url) return img.url;
                return null;
            }).filter(Boolean);

            const coords = addr.coords || item.coords || {};
            const lat = coords.lat || coords.latitude || '';
            const lon = coords.lon || coords.longitude || '';
            const fullAddr = [addr.street?.text, addr.house?.number, addr.neighborhood?.text, addr.city?.text].filter(Boolean).join(', ');

            items.push({
                listing_id: listingId,
                address: addr.street?.text || item.title_1 || '',
                house_number: addr.house?.number || '',
                neighborhood: addr.neighborhood?.text || item.title_2 || '',
                city: addr.city?.text || '',
                price: parsePrice(item.price),
                rooms: item.additionalDetails?.roomsCount || item.rooms || '',
                floor: addr.house?.floor ?? item.floor ?? '',
                size: item.additionalDetails?.squareMeter || item.square_meters || '',
                image_urls: images.slice(0, 5),
                listing_url: listingId ? 'https://www.yad2.co.il/realestate/item/' + listingId : '',
                google_maps_url: lat && lon ? `https://www.google.com/maps?q=${lat},${lon}` : (fullAddr ? `https://www.google.com/maps/search/${encodeURIComponent(fullAddr)}` : ''),
                coordinates: lat && lon ? {lat, lon} : null,
            });
        }
        function walk(obj, depth) {
            if (depth > 8 || items.length >= limit) return;
            if (Array.isArray(obj)) {
                for (const entry of obj) {
                    if (items.length >= limit) return;
                    if (looksLikeListing(entry)) push(entry);
                    else walk(entry, depth + 1);
                }
            } else if (obj && typeof obj === 'object') {
                for (const key of Object.keys(obj)) walk(obj[key], depth + 1);
            }
        }
        walk(pp.feed ?? {}, 0);
        if (!items.length) walk(pp.dehydratedState ?? {}, 0);
        if (!items.length) walk(pp, 0);
        if (items.length) return {items: items, count: items.length, source: 'next_data'};

        const links = Array.from(document.querySelectorAll('a[href*="/item/"]')).slice(0, limit);
        for (const a of links) {
            const idMatch = a.href.match(/\\/item\\/([a-z0-9]+)/i);
            const text = (a.innerText || '').trim().replace(/\\s+/g, ' ').slice(0, 200);
            if (!idMatch && !text) continue;
            const priceMatch = text.match(/([0-9][0-9,.]*)\\s*₪|₪\\s*([0-9][0-9,.]*)/);
            items.push({
                listing_id: idMatch ? idMatch[1] : '',
                address: text,
                house_number: '', neighborhood: '', city: '',
                price: priceMatch ? parsePrice(priceMatch[1] || priceMatch[2]) : 0,
                rooms: '', floor: '', size: '',
                image_urls: [],
                listing_url: a.href,
                google_maps_url: '',
                coordinates: null,
            });
        }
        if (items.length) return {items: items, count: items.length, source: 'dom'};

        const bodyTxt = document.body?.innerText || '';
        const emptyMarkers = ['לא נמצאו', 'לא מצאנו', 'אין תוצאות', '0 מודעות'];
        if (emptyMarkers.some(t => bodyTxt.includes(t))) return {items: [], count: 0, source: 'empty_state'};
        return {error: 'extracted 0 listings from a live page',
                title: document.title,
                page_props_keys: Object.keys(pp).join(',')};
    } catch(e) {
        return {error: e.message};
    }
}"""


def _build_search_url(city_code: str, min_rooms: int | None, max_rooms: int | None) -> str:
    """Build the rent-feed URL, restricted to crawler-sanctioned query parameters.

    Yad2's robots.txt disallows ``/*?*price=`` (along with floor, squaremeter and most other
    facet filters) for every user agent, while ``city`` and ``rooms`` appear in Yad2's own
    published sitemaps. Price is therefore filtered after extraction instead.
    """
    params = f"city={city_code}"
    if min_rooms or max_rooms:
        params += f"&rooms={min_rooms or 1}-{max_rooms or 12}"
    return f"https://www.yad2.co.il/realestate/rent?{params}"


def _apply_price_cap(items: list[dict], max_price: int | None, limit: int) -> list[dict]:
    """Drop over-budget listings, then truncate to ``limit``.

    Listings whose price could not be parsed are kept: an unknown price is not evidence of an
    over-budget one, and silently hiding them would understate the market.
    """
    if max_price:
        items = [i for i in items if not i.get("price") or i["price"] <= max_price]
    return items[:limit]


async def _scrape_yad2(city_code: str, max_price: int | None, min_rooms: int | None, max_rooms: int | None, limit: int) -> dict:
    """Run patchright to scrape Yad2 listings.

    Returns the raw extraction result: ``{"items": [...]}`` on success, or ``{"error": ...,
    "title": ..., "body": ...}`` when the listings payload could not be read (e.g. the site
    served a bot-verification page instead of the feed, or the page structure changed).

    ``max_price`` is applied after extraction rather than as a query parameter: Yad2's
    robots.txt disallows ``/*?*price=`` for every user agent, while ``city``/``rooms`` are
    crawler-sanctioned (they appear in Yad2's own published sitemaps).
    """
    from patchright.async_api import async_playwright

    url = _build_search_url(city_code, min_rooms, max_rooms)
    # Filtering client-side means the page must supply enough candidates to survive the cut.
    fetch_limit = min(limit * 6, 60) if max_price else limit

    async with async_playwright() as p:
        launch_kwargs: dict[str, Any] = {
            "headless": True,
            "args": ["--no-sandbox", "--disable-dev-shm-usage"],
        }
        if _PROXY_SERVER:
            proxy: dict[str, str] = {"server": _PROXY_SERVER}
            if _PROXY_USERNAME:
                proxy["username"] = _PROXY_USERNAME
                proxy["password"] = _PROXY_PASSWORD
            launch_kwargs["proxy"] = proxy
        try:
            # Full Chromium in new-headless mode: a far more real-Chrome-like fingerprint
            # than the default headless shell.
            browser = await p.chromium.launch(channel="chromium", **launch_kwargs)
        except Exception:
            browser = await p.chromium.launch(**launch_kwargs)

        # Advertise the engine's real major version — a UA/runtime version mismatch is a bot signal.
        major = browser.version.split(".")[0]
        context = await browser.new_context(
            user_agent=f"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="he-IL",
            timezone_id="Asia/Jerusalem",
        )
        page = await context.new_page()

        await page.goto(url, wait_until="domcontentloaded", timeout=30000)

        # Radware's interstitial runs a fingerprint probe before handing over the feed. It posts
        # its verdict within a few seconds and, when it decides "bot", simply keeps serving the
        # interstitial — it never auto-resolves and reloading does not help. So poll briefly,
        # then give up rather than burning half a minute per call.
        has_next_data = False
        page_title = ""
        challenged = False
        for _ in range(5):
            await page.wait_for_timeout(2000)
            state = await page.evaluate(
                "() => ({title: document.title, hasNext: !!document.getElementById('__NEXT_DATA__'),"
                " challenge: !!document.querySelector('script[src*=\"stormcaster\"]')})"
            )
            page_title = state["title"]
            challenged = challenged or state["challenge"]
            if state["hasNext"]:
                has_next_data = True
                break

        if not has_next_data:
            body_text = await page.evaluate("() => (document.body?.innerText || '').slice(0, 200)")
            await browser.close()
            return {
                "error": "bot_challenge" if challenged else "no __NEXT_DATA__",
                "title": page_title,
                "body": body_text,
            }

        listings = await page.evaluate(_EXTRACT_JS, fetch_limit)

        # Price is filtered here rather than in the query string (see docstring).
        if isinstance(listings, dict) and listings.get("items"):
            listings["items"] = _apply_price_cap(listings["items"], max_price, limit)
            listings["count"] = len(listings["items"])

        # If no images from __NEXT_DATA__, try to get them from individual listing pages.
        # Each visit is another request against a bot-scored origin, so cap the backfill.
        if isinstance(listings, dict) and listings.get("items"):
            for item in listings["items"][:3]:
                if not item.get("image_urls") and item.get("listing_id"):
                    try:
                        await page.goto(f"https://www.yad2.co.il/realestate/item/{item['listing_id']}", wait_until="domcontentloaded", timeout=15000)
                        await page.wait_for_timeout(2000)
                        images = await page.evaluate("""() => {
                            const imgs = document.querySelectorAll('img[src*="yad2"], img[src*="cloudfront"]');
                            return Array.from(imgs).map(i => i.src).filter(s => s.includes('Pic') || s.includes('pic')).slice(0, 5);
                        }""")
                        if images:
                            item["image_urls"] = images
                    except Exception as e:
                        await logger.adebug("yad2_image_scrape_failed", error=str(e))

        await browser.close()
        return listings if isinstance(listings, dict) else {"error": "unexpected extraction result"}


class Yad2SearchTool(BaseTool):
    name = "yad2_search"
    description = "Search Yad2 for apartments for rent. Returns structured listings with address, price, rooms, and image URLs."
    parameters_schema = {
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "City name (e.g. 'tel aviv', 'jerusalem') or city code (e.g. '5000').",
            },
            "max_price": {
                "type": "integer",
                "description": "Maximum monthly rent in ILS. Applied after fetching, so a tight "
                "cap may return fewer than `limit` results even when the market is not empty.",
            },
            "min_rooms": {
                "type": "integer",
                "description": "Minimum number of rooms.",
            },
            "max_rooms": {
                "type": "integer",
                "description": "Maximum number of rooms.",
            },
            "limit": {
                "type": "integer",
                "description": "Number of results to return (default 5, max 10).",
                "default": 5,
            },
        },
        "required": ["city"],
    }

    async def execute(
        self, city: str, max_price: int | None = None, min_rooms: int | None = None,
        max_rooms: int | None = None, limit: int = 5, **kwargs: Any,
    ) -> ToolResult:
        # Resolve city code
        city_code = city if city.isdigit() else CITY_CODES.get(city.lower().strip(), "")
        if not city_code:
            return ToolResult(success=False, error=f"Unknown city: {city}. Use a city code or one of: {', '.join(CITY_CODES.keys())}")

        limit = min(max(limit, 1), 10)

        try:
            await logger.ainfo("yad2_search_start", city=city_code, max_price=max_price, min_rooms=min_rooms)
            result = await _scrape_yad2(city_code, max_price, min_rooms, max_rooms, limit)

            if result.get("error"):
                title = result.get("title", "")
                body = result.get("body", "")
                await logger.awarning("yad2_scrape_blocked", reason=result["error"], page_title=title)
                blocked = (
                    result["error"] == "bot_challenge"
                    or "radware" in title.lower()
                    or "verifying your browser" in body.lower()
                )
                if blocked:
                    return ToolResult(
                        success=False,
                        error=(
                            "Yad2 served a bot-verification page (Radware) instead of listings — "
                            "the source is blocking automated access, so results are unavailable. "
                            "This is NOT an empty market; do not report 'no listings'. "
                            "The block is decided per request from the browser fingerprint and "
                            "source IP, so one retry may succeed; if it keeps recurring the "
                            "fingerprint has stopped clearing and needs code-side attention, or "
                            "the host IP needs routing through a proxy (YAD2_PROXY_SERVER)."
                        ),
                    )
                if result["error"].startswith("extracted 0 listings"):
                    return ToolResult(
                        success=False,
                        error=(
                            "Yad2 page loaded but no listings could be extracted — the page structure "
                            "may have changed. This is NOT confirmation of an empty market; "
                            "do not report 'no listings'."
                        ),
                    )
                return ToolResult(success=False, error=f"Yad2 scrape failed: {result['error']}")

            listings = result.get("items", [])
            await logger.ainfo("yad2_search_done", count=len(listings), source=result.get("source", ""))

            if not listings:
                return ToolResult(output="No listings found matching your criteria.", metadata={"count": 0})

            return ToolResult(
                output=json.dumps(listings, ensure_ascii=False, indent=2),
                metadata={"count": len(listings)},
            )
        except Exception as e:
            await logger.aerror("yad2_search_error", error=str(e))
            return ToolResult(success=False, error=f"Yad2 search failed: {str(e)[:200]}")
