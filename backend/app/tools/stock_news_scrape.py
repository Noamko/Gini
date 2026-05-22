"""Stock news scraper — uses stealth Playwright to scrape financial news sites."""
import json
from typing import Any

import structlog

from app.tools.base import BaseTool, ToolResult

logger = structlog.get_logger("stock_news_scrape")

# Supported news sources and their scraping configs
NEWS_SOURCES = {
    "yahoo_finance": {
        "url": "https://finance.yahoo.com/topic/stock-market-news/",
        "description": "Yahoo Finance stock market news",
    },
    "marketwatch": {
        "url": "https://www.marketwatch.com/latest-news",
        "description": "MarketWatch latest financial news",
    },
    "reuters": {
        "url": "https://www.reuters.com/business/",
        "description": "Reuters business news",
    },
    "cnbc": {
        "url": "https://www.cnbc.com/world/?region=world",
        "description": "CNBC world markets",
    },
    "seeking_alpha": {
        "url": "https://seekingalpha.com/market-news",
        "description": "Seeking Alpha market news",
    },
    "finviz": {
        "url": "https://finviz.com/news.ashx",
        "description": "Finviz aggregated financial news",
    },
}


async def _scrape_news(url: str, limit: int) -> list[dict]:
    """Use stealth Playwright to scrape news headlines and links."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            timezone_id="America/New_York",
        )
        page = await context.new_page()
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = { runtime: {} };
        """)

        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)

        # Generic headline extraction — looks for links within article/headline containers
        articles = await page.evaluate("""(limit) => {
            const seen = new Set();
            const results = [];

            // Strategy 1: Find article-like containers with headlines
            const selectors = [
                'article h2 a', 'article h3 a', 'article h4 a',
                '[class*="headline"] a', '[class*="title"] a',
                '[class*="story"] h2 a', '[class*="story"] h3 a',
                '[data-testid*="title"] a', '[data-testid*="headline"] a',
                'h2 a[href*="/"]', 'h3 a[href*="/"]',
                '.js-stream-content a', '.content-list a',
            ];

            for (const sel of selectors) {
                if (results.length >= limit) break;
                for (const el of document.querySelectorAll(sel)) {
                    if (results.length >= limit) break;
                    const title = (el.textContent || '').trim();
                    const href = el.href || '';
                    if (title.length > 15 && title.length < 300 && href && !seen.has(title)) {
                        seen.add(title);
                        // Try to find a date nearby
                        let date = '';
                        const parent = el.closest('article') || el.closest('[class*="story"]') || el.parentElement?.parentElement;
                        if (parent) {
                            const timeEl = parent.querySelector('time');
                            if (timeEl) date = timeEl.getAttribute('datetime') || timeEl.textContent || '';
                        }
                        results.push({ title, link: href, published: date.trim() });
                    }
                }
            }

            // Strategy 2: Fallback — scan all links if we found too few
            if (results.length < 3) {
                for (const a of document.querySelectorAll('a[href]')) {
                    if (results.length >= limit) break;
                    const title = (a.textContent || '').trim();
                    const href = a.href || '';
                    if (title.length > 30 && title.length < 300 && href.includes('/') && !seen.has(title)
                        && !href.includes('login') && !href.includes('subscribe') && !href.includes('#')) {
                        seen.add(title);
                        results.push({ title, link: href, published: '' });
                    }
                }
            }

            return results;
        }""", limit)

        await browser.close()
        return articles


class StockNewsScrapeTool(BaseTool):
    name = "stock_news_scrape"
    description = (
        "Scrape financial news headlines from major sites using a stealth browser. "
        "Bypasses paywalls and anti-bot protection. Sources: yahoo_finance, marketwatch, "
        "reuters, cnbc, seeking_alpha, finviz. Can also scrape any custom URL."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
                "description": (
                    "News source alias (yahoo_finance, marketwatch, reuters, cnbc, seeking_alpha, finviz) "
                    "or a full URL to scrape."
                ),
            },
            "limit": {
                "type": "integer",
                "description": "Max headlines to return (default 15, max 30).",
                "default": 15,
            },
        },
        "required": ["source"],
    }

    async def execute(self, source: str, limit: int = 15, **kwargs: Any) -> ToolResult:
        limit = min(max(limit, 1), 30)

        if source.lower().strip() in NEWS_SOURCES:
            config = NEWS_SOURCES[source.lower().strip()]
            url = config["url"]
            source_name = config["description"]
        elif source.startswith("http"):
            url = source
            source_name = url
        else:
            aliases = ", ".join(NEWS_SOURCES.keys())
            return ToolResult(success=False, error=f"Unknown source: {source}. Available: {aliases}. Or pass a full URL.")

        try:
            await logger.ainfo("stock_scrape_start", source=source, url=url[:80])
            articles = await _scrape_news(url, limit)
            await logger.ainfo("stock_scrape_done", source=source, count=len(articles))

            if not articles:
                return ToolResult(
                    output=f"No headlines found from {source_name}. The site may have changed its layout.",
                    metadata={"source": source, "count": 0},
                )

            return ToolResult(
                output=json.dumps(articles, ensure_ascii=False, indent=2),
                metadata={"source": source, "count": len(articles)},
            )
        except Exception as e:
            await logger.aerror("stock_scrape_error", source=source, error=str(e))
            return ToolResult(success=False, error=f"Scrape failed for {source}: {str(e)[:200]}")
