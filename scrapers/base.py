import abc
import asyncio
import json
import logging
import os
import random
import re
import time
from pathlib import Path
from typing import List, Tuple
from urllib.parse import urljoin

from playwright.async_api import Page, async_playwright


class BaseScraper(abc.ABC):
    """Abstract async base scraper providing browser/context lifecycle,
    retries, timeouts and simple helpers.

    Subclasses must implement:
      - async get_category_urls() -> List[Tuple[str, str]]  # (url, category_name)
      - async scrape_category(page: Page, category_url: str, category_name: str) -> List[dict]
    """

    def __init__(
        self, shop_id: str, shop_name: str, base_url: str, headless: bool = True
    ):
        self.shop_id = shop_id
        self.shop_name = shop_name
        self.base_url = base_url.rstrip("/")
        self.headless = headless
        self._browser = None
        self._context = None
        self._playwright = None
        self.logger = logging.getLogger(f"scraper.{shop_id}")

        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
        ]

        # tuning
        self.page_timeout = 30000
        self.max_page_retries = 2

        # category filtering
        self.allowed_categories = {"gpu", "cpu"}
        self.category_keywords = {
            "gpu": [
                "placa",
                "placas",
                "video",
                "gpu",
                "rtx",
                "gtx",
                "rx",
                "radeon",
                "geforce",
            ],
            "cpu": [
                "procesador",
                "procesadores",
                "cpu",
                "ryzen",
                "intel",
                "core",
                "athlon",
            ],
        }

    async def _start(self):
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.headless)

    async def _stop(self):
        try:
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception:
            pass

    async def _new_context(self):
        ctx = await self._browser.new_context(
            user_agent=random.choice(self.user_agents)
        )
        return ctx

    async def _fetch_page(self, page: Page, url: str) -> bool:
        """Navigate with retry logic and stronger load handling. Returns True on success."""
        for attempt in range(1, self.max_page_retries + 1):
            try:
                await page.goto(
                    url, timeout=self.page_timeout, wait_until="domcontentloaded"
                )
                await page.wait_for_load_state("networkidle", timeout=self.page_timeout)
                await asyncio.sleep(random.uniform(0.6, 1.5))
                return True
            except Exception as e:
                self.logger.warning(
                    "goto failed (%s) attempt %d/%d: %s",
                    url,
                    attempt,
                    self.max_page_retries,
                    e,
                )
                await asyncio.sleep(1 + attempt)
        return False

    def _normalize_category_name(self, category_name: str | None) -> str:
        if not category_name:
            return ""
        return category_name.strip().lower()

    def _is_category_match(self, category_name: str | None, title: str | None) -> bool:
        """Return True if category_name/title looks like GPU or CPU."""
        cat = self._normalize_category_name(category_name)
        title_l = (title or "").lower()
        # direct category match (use flexible matching: word-boundary, plurals, or substring fallback)
        import re

        def _contains_word(text: str, keyword: str, allow_substring: bool = True) -> bool:
            if not keyword or not text:
                return False
            kw = keyword.lower()
            # exact word match
            if re.search(r"\b" + re.escape(kw) + r"\b", text):
                return True
            # plural/singular variants
            if re.search(r"\b" + re.escape(kw + 's') + r"\b", text):
                return True
            if kw.endswith('s') and re.search(r"\b" + re.escape(kw.rstrip('s')) + r"\b", text):
                return True
            # fallback substring (only allowed for title matching)
            if allow_substring:
                return kw in text
            return False

        # Prefer title-based matching (more specific). Only if title lacks clues,
        # allow strict matching against the category name (no substring fallback)
        for k in self.category_keywords["gpu"]:
            if _contains_word(title_l, k, allow_substring=True):
                return True
        for k in self.category_keywords["cpu"]:
            if _contains_word(title_l, k, allow_substring=True):
                return True

        # Title had no hints — use category name but be conservative (no substring fallback)
        for k in self.category_keywords["gpu"]:
            if _contains_word(cat, k, allow_substring=False):
                return True
        for k in self.category_keywords["cpu"]:
            if _contains_word(cat, k, allow_substring=False):
                return True

        return False

    def _parse_price_text(self, text: str | None) -> int | None:
        """Parse price from mixed text (supports offer/regular formats)."""
        if not text:
            return None
        txt = text.replace("\xa0", " ").replace(".", "").replace(",", ".")
        matches = re.findall(r"(\d+(?:\.\d+)?)", txt)
        if not matches:
            return None
        try:
            # pick the largest numeric value (often the real price in mixed strings)
            nums = [float(m) for m in matches]
            # Use truncation to drop fractional cents and keep integer currency units
            return int(max(nums))
        except Exception:
            return None

    def _debug_enabled(self) -> bool:
        return os.getenv("SCRAPER_DEBUG") == "1"

    def _debug_dir(self, shop_id: str) -> Path:
        root = Path(__file__).resolve().parents[1] / "debug" / shop_id
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _write_debug_artifacts(
        self,
        shop_id: str,
        url: str,
        selector: str,
        node_count: int,
        wait_ms: int,
        container_html: str,
    ) -> None:
        if not self._debug_enabled():
            return
        debug_dir = self._debug_dir(shop_id)
        meta = {
            "shop_id": shop_id,
            "url": url,
            "selector": selector,
            "node_count": node_count,
            "wait_ms": wait_ms,
            "timestamp": time.time(),
        }
        (debug_dir / "dom.html").write_text(container_html or "", encoding="utf-8")
        (debug_dir / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    async def _wait_random(self, a=0.5, b=1.5):
        await asyncio.sleep(random.uniform(a, b))

    @abc.abstractmethod
    async def get_category_urls(self) -> List[Tuple[str, str]]:
        """Return list of (category_url, category_name) to scrape."""

    @abc.abstractmethod
    async def scrape_category(
        self, page: Page, category_url: str, category_name: str
    ) -> List[dict]:
        """Scrape given category page(s) and return list of product dicts."""

    async def run(self, limit_per_category: int | None = None) -> List[dict]:
        """Main entry: start browser, iterate categories and collect results."""
        await self._start()
        results = []
        try:
            self._context = await self._new_context()
            page = await self._context.new_page()
            categories = await self.get_category_urls()
            for url, category_name in categories:
                try:
                    ok = await self._fetch_page(page, url)
                    if not ok:
                        self.logger.error("Failed to load category %s", url)
                        continue
                    items = await self.scrape_category(page, url, category_name)
                    if limit_per_category:
                        items = items[:limit_per_category]
                    results.extend(items)
                    await self._wait_random(1.0, 2.0)
                except Exception:
                    self.logger.exception("Error scraping category %s", url)
                    continue
        finally:
            await self._stop()

        return results

    def _abs_url(self, href: str) -> str:
        return urljoin(self.base_url + "/", href)
