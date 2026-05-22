"""RSS/Atom feed fetcher — parses feeds and returns structured entries."""
import json
from typing import Any
from xml.etree import ElementTree

import httpx
import structlog

from app.tools.base import BaseTool, ToolResult

logger = structlog.get_logger("rss_fetch")

# Common financial news RSS feeds
KNOWN_FEEDS = {
    "google_news_business": "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx6TVdZU0FtVnVHZ0pWVXlnQVAB",
    "google_news_markets": "https://news.google.com/rss/search?q=stock+market+news&hl=en&gl=US&ceid=US:en",
    "yahoo_finance": "https://finance.yahoo.com/news/rssindex",
    "reuters_business": "https://www.reutersagency.com/feed/?best-topics=business-finance",
    "cnbc_top": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114",
    "marketwatch": "https://feeds.marketwatch.com/marketwatch/topstories/",
    "seeking_alpha": "https://seekingalpha.com/market_currents.xml",
    "motley_fool": "https://www.fool.com/feeds/index.aspx",
    "investopedia": "https://www.investopedia.com/feedbuilder/feed/getfeed/?feedName=rss_headline",
}


def _parse_feed(xml_text: str, limit: int) -> list[dict]:
    """Parse RSS or Atom XML into structured entries."""
    root = ElementTree.fromstring(xml_text)

    entries = []

    # RSS 2.0 format
    for item in root.iter("item"):
        if len(entries) >= limit:
            break
        entry = {
            "title": (item.findtext("title") or "").strip(),
            "link": (item.findtext("link") or "").strip(),
            "published": (item.findtext("pubDate") or "").strip(),
            "description": (item.findtext("description") or "").strip()[:500],
            "source": (item.findtext("source") or "").strip(),
        }
        if entry["title"]:
            entries.append(entry)

    # Atom format (if no RSS items found)
    if not entries:
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for item in root.findall(".//atom:entry", ns):
            if len(entries) >= limit:
                break
            link_el = item.find("atom:link", ns)
            entry = {
                "title": (item.findtext("atom:title", namespaces=ns) or "").strip(),
                "link": link_el.get("href", "") if link_el is not None else "",
                "published": (item.findtext("atom:published", namespaces=ns) or item.findtext("atom:updated", namespaces=ns) or "").strip(),
                "description": (item.findtext("atom:summary", namespaces=ns) or "").strip()[:500],
                "source": "",
            }
            if entry["title"]:
                entries.append(entry)

    return entries


class RssFetchTool(BaseTool):
    name = "rss_fetch"
    description = (
        "Fetch and parse an RSS/Atom feed. Returns structured entries with title, link, date, and description. "
        "Can use a known feed alias (e.g. 'google_news_business', 'yahoo_finance', 'cnbc_top', 'marketwatch', "
        "'reuters_business', 'seeking_alpha', 'motley_fool') or a custom feed URL."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "feed": {
                "type": "string",
                "description": (
                    "Feed alias or full URL. Aliases: google_news_business, google_news_markets, "
                    "yahoo_finance, reuters_business, cnbc_top, marketwatch, seeking_alpha, motley_fool, investopedia."
                ),
            },
            "limit": {
                "type": "integer",
                "description": "Max entries to return (default 15, max 30).",
                "default": 15,
            },
        },
        "required": ["feed"],
    }

    async def execute(self, feed: str, limit: int = 15, **kwargs: Any) -> ToolResult:
        url = KNOWN_FEEDS.get(feed.lower().strip(), feed)
        limit = min(max(limit, 1), 30)

        if not url.startswith("http"):
            aliases = ", ".join(KNOWN_FEEDS.keys())
            return ToolResult(success=False, error=f"Unknown feed alias: {feed}. Available: {aliases}")

        try:
            await logger.ainfo("rss_fetch_start", feed=feed, url=url[:80])
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                resp = await client.get(url, headers={
                    "User-Agent": "Mozilla/5.0 (compatible; GiniBot/1.0)",
                    "Accept": "application/rss+xml, application/xml, text/xml",
                })
                resp.raise_for_status()

            entries = _parse_feed(resp.text, limit)
            await logger.ainfo("rss_fetch_done", feed=feed, count=len(entries))

            if not entries:
                return ToolResult(output="No entries found in this feed.", metadata={"feed": feed, "count": 0})

            return ToolResult(
                output=json.dumps(entries, ensure_ascii=False, indent=2),
                metadata={"feed": feed, "count": len(entries)},
            )
        except ElementTree.ParseError as e:
            return ToolResult(success=False, error=f"Failed to parse feed XML: {str(e)[:200]}")
        except httpx.HTTPStatusError as e:
            return ToolResult(success=False, error=f"HTTP {e.response.status_code}: {e.response.reason_phrase}")
        except Exception as e:
            await logger.aerror("rss_fetch_error", error=str(e))
            return ToolResult(success=False, error=f"RSS fetch failed: {str(e)[:200]}")
