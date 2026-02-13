import logging
import re
import time
from datetime import datetime
from typing import List, Tuple

from playwright.async_api import Page

from .base import BaseScraper


class CompraGamerScraper(BaseScraper):
    def __init__(
        self,
        shop_id: str = "compra_gamer",
        shop_name: str = "Compra Gamer",
        base_url: str = "https://compragamer.com",
        headless: bool = True,
    ):
        super().__init__(shop_id, shop_name, base_url, headless=headless)
        self.logger = logging.getLogger("scraper.compra_gamer")

    async def get_category_urls(self) -> List[Tuple[str, str]]:
        # Use "agrup" endpoints which list all products for the group and use infinite scroll.
        return [
            (f"{self.base_url}/productos?agrup=7", "Procesadores"),
            (f"{self.base_url}/productos?agrup=2", "Placas de video"),
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

    def _matches_category(self, category_name: str, title: str) -> bool:
        # Delegate to BaseScraper robust matcher (uses word-boundary matching).
        return self._is_category_match(category_name, title)

    async def scrape_category(
        self, page: Page, category_url: str, category_name: str
    ) -> List[dict]:
        results = []
        seen_urls: set[str] = set()

        self.logger.info(
            "Scraping %s (infinite scroll): %s", category_name, category_url
        )
        try:
            await page.goto(category_url)
            await page.wait_for_timeout(800)
        except Exception as e:
            self.logger.warning("Failed loading page %s: %s", category_url, e)
            return results

        # CompraGamer usa Angular y `.ng-star-inserted` aparece en navegación/header/footer.
        # La regla para no traer basura: solo contar/parsear elementos que contengan links de producto.
        product_link_selector = "a[href*='/producto/']"

        # Infinite scroll: scroll down until no new *product links* appear for a few iterations.
        max_scroll_rounds = 120
        stable_rounds_needed = 5
        stable_rounds = 0
        last_count = 0

        for _ in range(max_scroll_rounds):
            try:
                await page.evaluate(
                    "() => window.scrollTo(0, document.body.scrollHeight)"
                )
            except Exception:
                pass
            await page.wait_for_timeout(950)

            try:
                current_count = await page.eval_on_selector_all(
                    product_link_selector,
                    "els => els.length",
                )
            except Exception:
                current_count = 0

            if current_count <= last_count:
                stable_rounds += 1
            else:
                stable_rounds = 0
                last_count = current_count

            if stable_rounds >= stable_rounds_needed:
                break

        # After scroll, parse product containers.
        # Use ng-star-inserted but filter them by presence of a product link to avoid nav elements.
        cards = await page.query_selector_all(
            f".ng-star-inserted:has({product_link_selector})"
        )
        self.logger.info(
            "Found %d candidate cards after scroll for %s", len(cards), category_name
        )

        for c in cards:
            try:
                a = await c.query_selector(product_link_selector)
                href = await a.get_attribute("href") if a else None
                if not href:
                    continue

                url = href if href.startswith("http") else self._abs_url(href)

                title = None
                for tsel in [
                    "h2",
                    "h3",
                    ".title",
                    ".product-title",
                    "a > span",
                ]:
                    el = await c.query_selector(tsel)
                    if el:
                        title = (await el.inner_text()).strip()
                        if title:
                            break

                # Fallback: use the product link text as title if needed (not nav, because link is /producto/)
                if not title and a:
                    try:
                        t = (await a.inner_text()).strip()
                    except Exception:
                        t = ""
                    title = t or None

                if title and not self._matches_category(category_name, title):
                    continue

                price = None
                price_texts = []

                for psel in [
                    ".price",
                    ".product-price",
                    ".precio",
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

                if price is None:
                    try:
                        card_text = await c.inner_text()
                    except Exception:
                        card_text = None
                    price = self._parse_price(card_text) if card_text else None

                stock = True
                for ssel in [
                    ".stock",
                    ".availability",
                    ".unavailable",
                    ".sold-out",
                    ".sin-stock",
                ]:
                    sel = await c.query_selector(ssel)
                    if sel:
                        st = (await sel.inner_text()).lower()
                        if "agot" in st or "sin stock" in st or "no hay" in st:
                            stock = False
                        break

                if url in seen_urls:
                    continue
                seen_urls.add(url)

                # Filter irrelevant peripherals (headsets, mics, cables, etc.)
                if not self._is_relevant_product(title, category_name):
                    continue

                results.append(
                    {
                        "shop_id": self.shop_id,
                        "shop_name": self.shop_name,
                        "category": category_name,
                        "product_name": (title or "").upper(),
                        "price": int(price) if price is not None else None,
                        "stock": bool(stock),
                        "product_url": url,
                        "scraped_at": datetime.utcnow().isoformat(),
                    }
                )
            except Exception:
                self.logger.exception("product parse error")
                continue

        return results


if __name__ == "__main__":
    import asyncio
    import logging

    logging.basicConfig(level=logging.INFO)
    s = CompraGamerScraper()
    data = asyncio.run(s.run(limit_per_category=10))
    print("Scraped", len(data))
