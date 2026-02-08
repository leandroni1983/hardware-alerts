import logging
import re
import time
from datetime import datetime
from typing import List, Tuple

from playwright.async_api import Page

from .base import BaseScraper


class FullH4rdScraper(BaseScraper):
    def __init__(
        self,
        shop_id: str = "fullh4rd",
        shop_name: str = "FullH4rd",
        base_url: str = "https://fullh4rd.com.ar",
        headless: bool = True,
    ):
        super().__init__(shop_id, shop_name, base_url, headless=headless)
        self.logger = logging.getLogger("scraper.fullh4rd")

    async def get_category_urls(self) -> List[Tuple[str, str]]:
        return [
            (f"{self.base_url}/cat/search/placa%20de%20video", "Placas de video"),
            (f"{self.base_url}/cat/search/procesadores", "Procesadores"),
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
            return int(max(nums))
        except Exception:
            return None

    @staticmethod
    def _matches_category(category_name: str, title: str) -> bool:
        cat = (category_name or "").lower()
        t = (title or "").lower()
        gpu_keys = [
            "placa",
            "placas",
            "video",
            "gpu",
            "rtx",
            "gtx",
            "rx",
            "radeon",
            "geforce",
        ]
        cpu_keys = [
            "procesador",
            "procesadores",
            "cpu",
            "ryzen",
            "intel",
            "core",
            "athlon",
        ]
        if any(k in cat for k in gpu_keys):
            return any(k in t for k in gpu_keys)
        if any(k in cat for k in cpu_keys):
            return any(k in t for k in cpu_keys)
        return any(k in t for k in gpu_keys) or any(k in t for k in cpu_keys)

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

            # FullH4rd: las cards reales están dentro del listado con clase "item product-list".
            # Usamos ese selector primero para evitar enganchar bloques genéricos del sitio.
            card_selectors = [
                ".item.product-list",
                ".item.product-list a[href]",
                ".product-item",
                ".product-card",
                ".product-list-item",
                ".item-product",
                ".card-product",
                ".product__item",
                "li.product",
                ".product-list .product",
                ".product",
                ".producto",
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
                            'el => el.closest(".product, .product-item, .product-card, .product-list-item, .item-product, .card-product, .product__item, li.product, .producto, article, li, div")'
                        )
                        if parent:
                            cards.append(parent)

            for c in cards:
                try:
                    # Skip obvious non-product blocks that can be matched by generic selectors
                    try:
                        card_text_l = (await c.inner_text()).strip().lower()
                    except Exception:
                        card_text_l = ""

                    if (
                        "atención al cliente" in card_text_l
                        or "atencion al cliente" in card_text_l
                    ):
                        continue
                    if "whatsapp" in card_text_l and "send?" in card_text_l:
                        continue

                    title = None
                    for tsel in [
                        "h2",
                        "h3",
                        ".title",
                        ".product-title",
                        ".product-name",
                        ".product__title",
                        ".name",
                        ".nombre",
                        "a.title",
                        "a.product-link",
                    ]:
                        el = await c.query_selector(tsel)
                        if el:
                            title = (await el.inner_text()).strip()
                            break

                    a = await c.query_selector("a[href]")
                    href = await a.get_attribute("href") if a else None

                    # Ignore cards whose only meaningful link is to WhatsApp / support
                    if href and ("api.whatsapp.com/send" in href or "wa.me/" in href):
                        continue

                    # Fallback: if title wasn't found but we have a reasonable link text, use it
                    if not title and a:
                        try:
                            t = (await a.inner_text()).strip()
                        except Exception:
                            t = ""
                        title = t or None

                    if title and not self._is_category_match(category_name, title):
                        self.logger.debug("Filtered out by category: %s", title)
                        continue

                    url = href or category_url
                    if href and not href.startswith("http"):
                        url = self._abs_url(href)

                    price = None

                    # 1) Prefer explicit price nodes/attrs if present
                    price_texts = []
                    for psel in [
                        ".price",
                        ".precio",
                        ".product-price",
                        ".amount",
                        "[itemprop='price']",
                        "meta[itemprop='price']",
                    ]:
                        pel = await c.query_selector(psel)
                        if pel:
                            try:
                                price_texts.append(await pel.inner_text())
                            except Exception:
                                pass
                            for attr in [
                                "data-price",
                                "data-final-price",
                                "data-amount",
                                "data-precio",
                                "content",
                                "value",
                            ]:
                                data = await pel.get_attribute(attr)
                                if data:
                                    price_texts.append(data)

                    for attr in [
                        "data-price",
                        "data-final-price",
                        "data-amount",
                        "data-precio",
                    ]:
                        data = await c.get_attribute(attr)
                        if data:
                            price_texts.append(data)

                    for txt in price_texts:
                        parsed = self._parse_price(txt)
                        if parsed:
                            price = parsed if price is None else max(price, parsed)

                    # 2) Fallback: parse from the entire card text (sometimes price has no stable class)
                    if price is None:
                        price = self._parse_price(card_text_l) if card_text_l else None

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
    s = FullH4rdScraper()
    data = asyncio.run(s.run(limit_per_category=10))
    print("Scraped", len(data))
