"""Yad2 apartment search tool — uses stealth Playwright to scrape listings."""
import asyncio
import json
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


async def _scrape_yad2(city_code: str, max_price: int | None, min_rooms: int | None, max_rooms: int | None, limit: int) -> list[dict]:
    """Run stealth Playwright to scrape Yad2 listings."""
    from playwright.async_api import async_playwright

    params = f"city={city_code}"
    if max_price:
        params += f"&price=-{max_price}"
    if min_rooms or max_rooms:
        r_min = min_rooms or 1
        r_max = max_rooms or 12
        params += f"&rooms={r_min}-{r_max}"

    url = f"https://www.yad2.co.il/realestate/rent?{params}"

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="he-IL",
            timezone_id="Asia/Jerusalem",
        )
        page = await context.new_page()
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = { runtime: {} };
        """)

        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(4000)

        # Extract listings from __NEXT_DATA__
        listings = await page.evaluate("""(limit) => {
            try {
                const el = document.getElementById('__NEXT_DATA__');
                if (!el) return {error: 'no __NEXT_DATA__'};
                const d = JSON.parse(el.textContent);
                const feed = d.props?.pageProps?.feed;
                if (!feed) return {error: 'no feed'};

                let items = [];
                function findItems(obj, depth) {
                    if (depth > 4 || items.length >= limit) return;
                    if (Array.isArray(obj)) {
                        for (const item of obj) {
                            if (items.length >= limit) return;
                            if (item && typeof item === 'object' && (item.address || item.title_1 || item.price)) {
                                const addr = item.address || {};
                                const images = (item.images || item.media?.pics || []).map(img => {
                                    if (typeof img === 'string') return img;
                                    if (img.src) return img.src;
                                    if (img.url) return img.url;
                                    return null;
                                }).filter(Boolean);

                                const coords = addr.coords || item.coords || {};
                                const lat = coords.lat || '';
                                const lon = coords.lon || '';
                                const listingId = item.id || item.token || '';
                                const fullAddr = [addr.street?.text, addr.house?.number, addr.neighborhood?.text, addr.city?.text].filter(Boolean).join(', ');

                                items.push({
                                    listing_id: listingId,
                                    address: addr.street?.text || item.title_1 || '',
                                    house_number: addr.house?.number || '',
                                    neighborhood: addr.neighborhood?.text || item.title_2 || '',
                                    city: addr.city?.text || '',
                                    price: item.price || 0,
                                    rooms: item.additionalDetails?.roomsCount || item.rooms || '',
                                    floor: addr.house?.floor ?? item.floor ?? '',
                                    size: item.additionalDetails?.squareMeter || item.square_meters || '',
                                    image_urls: images.slice(0, 5),
                                    listing_url: listingId ? 'https://www.yad2.co.il/realestate/item/' + listingId : '',
                                    google_maps_url: lat && lon ? `https://www.google.com/maps?q=${lat},${lon}` : (fullAddr ? `https://www.google.com/maps/search/${encodeURIComponent(fullAddr)}` : ''),
                                    coordinates: lat && lon ? {lat, lon} : null,
                                });
                            }
                        }
                    } else if (typeof obj === 'object' && obj !== null) {
                        for (const key of Object.keys(obj)) {
                            findItems(obj[key], depth + 1);
                        }
                    }
                }
                findItems(feed, 0);
                return {items: items, count: items.length};
            } catch(e) {
                return {error: e.message};
            }
        }""", limit)

        # If no images from __NEXT_DATA__, try to get them from individual listing pages
        if listings.get("items"):
            for item in listings["items"][:limit]:
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
                    except Exception:
                        pass

        await browser.close()
        return listings.get("items", []) if isinstance(listings, dict) else []


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
                "description": "Maximum monthly rent in ILS.",
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
            listings = await _scrape_yad2(city_code, max_price, min_rooms, max_rooms, limit)
            await logger.ainfo("yad2_search_done", count=len(listings))

            if not listings:
                return ToolResult(output="No listings found matching your criteria.", metadata={"count": 0})

            return ToolResult(
                output=json.dumps(listings, ensure_ascii=False, indent=2),
                metadata={"count": len(listings)},
            )
        except Exception as e:
            await logger.aerror("yad2_search_error", error=str(e))
            return ToolResult(success=False, error=f"Yad2 search failed: {str(e)[:200]}")
