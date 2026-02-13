import logging
import re
import time
from datetime import datetime
from typing import List, Tuple

from playwright.async_api import Page

from .base import BaseScraper


class GezatekScraper(BaseScraper):
    def __init__(
        self,
        shop_id: str = "gezatek",
        shop_name: str = "Gezatek",
        base_url: str = "https://www.gezatek.com.ar",
        headless: bool = True,
    ):
        super().__init__(shop_id, shop_name, base_url, headless=headless)
        self.logger = logging.getLogger("scraper.gezatek")

    async def get_category_urls(self) -> List[Tuple[str, str]]:
        return [
            (f"{self.base_url}/tienda/procesadores-amd/", "Procesadores"),
            (f"{self.base_url}/tienda/procesadores-intel/", "Procesadores"),
            (f"{self.base_url}/tienda/vga-nvidia/", "Placas de video"),
            (f"{self.base_url}/tienda/vga-amd/", "Placas de video"),
        ]

    @staticmethod
    def _parse_price(text: str) -> int | None:
        if not text:
            return None
        txt = text.replace("\xa0", " ").replace(".", "").replace(",", ".")
        matches = re.findall(r"(\d+(?:\.\d+)?)", txt)
        if not matches:
            return None
        try:
            nums = [float(m) for m in matches]
            # remove fractional cents: keep only whole currency units
            return int(max(nums))
        except Exception:
            return None

    def _matches_category(self, category_name: str, title: str) -> bool:
        return self._is_category_match(category_name, title)

    async def scrape_category(
        self, page: Page, category_url: str, category_name: str
    ) -> List[dict]:
        results = []
        next_url = category_url
        page_num = 0
        max_pages = 5

        while next_url and page_num < max_pages:
            page_num += 1
            self.logger.info(
                "Scraping %s page %d: %s", category_name, page_num, next_url
            )
            try:
                await page.goto(next_url)
                await page.wait_for_timeout(800)
            except Exception as e:
                self.logger.warning("Failed loading page %s: %s", next_url, e)
                break

            card_selectors = [
                ".w-box.product",
                ".w-box.product a[href]",
                ".product",
                ".product-item",
                "li.product",
                ".grid-item",
            ]
            expected_selector = card_selectors[0]
            wait_ms = 0

            if self._debug_enabled():
                t0 = time.monotonic()
                try:
                    await page.wait_for_selector(expected_selector, timeout=10000)
                except Exception as e:
                    self.logger.warning(
                        "Debug wait_for_selector failed for %s: %s",
                        expected_selector,
                        e,
                    )
                wait_ms = int((time.monotonic() - t0) * 1000)
                self.logger.info(
                    "Debug expected selector: %s (wait_ms=%d)",
                    expected_selector,
                    wait_ms,
                )

            cards = []
            for sel in card_selectors:
                elems = await page.query_selector_all(sel)
                if elems and len(elems) > 0:
                    cards = elems
                    break
            page_items = 0
            self.logger.info("Found %d product cards on page %d", len(cards), page_num)

            if self._debug_enabled():
                container_html = ""
                if cards:
                    try:
                        container_html = await cards[0].evaluate(
                            "el => (el.parentElement && el.parentElement.innerHTML) ? el.parentElement.innerHTML : el.outerHTML"
                        )
                    except Exception:
                        container_html = ""
                debug_dir = self._debug_dir(self.shop_id)
                await page.screenshot(
                    path=str(debug_dir / "screenshot.png"), full_page=True
                )
                self._write_debug_artifacts(
                    self.shop_id,
                    next_url,
                    expected_selector,
                    len(cards),
                    wait_ms,
                    container_html,
                )

            if not cards:
                anchors = await page.query_selector_all("a")
                for a in anchors:
                    href = await a.get_attribute("href") or ""
                    if "/producto/" in href or "/product/" in href:
                        parent = await a.evaluate_handle(
                            'el => el.closest("article, li, div")'
                        )
                        if parent:
                            cards.append(parent)

            for c in cards:
                try:
                    title = None
                    for tsel in ["h2", "h3", ".title", ".product-title", ".nombre"]:
                        el = await c.query_selector(tsel)
                        if el:
                            title = (await el.inner_text()).strip()
                            break

                    if title and not self._is_category_match(category_name, title):
                        self.logger.debug("Filtered out by category: %s", title)
                        continue

                    a = await c.query_selector("a")
                    href = await a.get_attribute("href") if a else None
                    url = href or category_url
                    if href and not href.startswith("http"):
                        url = self._abs_url(href)

                    price = None
                    price_texts = []
                    for psel in [".price", ".precio", ".product-price", ".amount"]:
                        pel = await c.query_selector(psel)
                        if pel:
                            price_texts.append(await pel.inner_text())
                    for txt in price_texts:
                        parsed = self._parse_price(txt)
                        if parsed:
                            price = parsed if price is None else max(price, parsed)

                    if price is None:
                        data = await c.get_attribute("data-price")
                        if data:
                            d = (data or "").strip()
                            # If data-price is a plain integer (likely cents),
                            # convert accordingly. Otherwise fall back to parser.
                            if re.fullmatch(r"\d+", d):
                                try:
                                    pv = int(d)
                                    if pv > 1_000_000:
                                        price = pv // 100
                                    else:
                                        price = pv
                                except Exception:
                                    price = self._parse_price(data)
                            else:
                                price = self._parse_price(data)

                    stock = True
                    for ssel in [".stock", ".availability", ".sin-stock", ".no-stock"]:
                        sel = await c.query_selector(ssel)
                        if sel:
                            st = (await sel.inner_text()).lower()
                            if "agot" in st or "sin stock" in st or "no hay" in st:
                                stock = False
                            break

                    product = {
                        "shop_id": self.shop_id,
                        "shop_name": self.shop_name,
                        "category": category_name,
                        "product_name": (title or "").upper(),
                        "price": int(price) if price is not None else None,
                        "stock": bool(stock),
                        "product_url": url,
                        "scraped_at": datetime.utcnow().isoformat(),
                    }
                    # Filter irrelevant peripherals (headsets, mics, cables, etc.)
                    if not self._is_relevant_product(title, category_name):
                        continue
                    results.append(product)
                    page_items += 1
                except Exception:
                    self.logger.exception("product parse error")
                    continue

            self.logger.info(
                "Parsed %d products on page %d for %s",
                page_items,
                page_num,
                category_name,
            )
            next_url = None
            try:
                nxt = await page.query_selector("a.next") or await page.query_selector(
                    ".pagination a.next"
                )
                if nxt:
                    href = await nxt.get_attribute("href")
                    if href:
                        next_url = (
                            href if href.startswith("http") else self._abs_url(href)
                        )
            except Exception:
                next_url = None

        return results


if __name__ == "__main__":
    import asyncio
    import logging

    logging.basicConfig(level=logging.INFO)
    s = GezatekScraper()
    data = asyncio.run(s.run(limit_per_category=10))
    print("Scraped", len(data))
