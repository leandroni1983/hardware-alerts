import logging
from typing import List, Dict, Any
from scrapers.compra_gamer import CompraGamerScraper
from scrapers.venex import VenexScraper
from scrapers.mexx import MexxScraper
from scrapers.fullh4rd import FullH4rdScraper
from scrapers.gezatek import GezatekScraper

logger = logging.getLogger("scraper_runner")

SCRAPER_CLASSES = {
    "compra_gamer": CompraGamerScraper,
    "venex": VenexScraper,
    "mexx": MexxScraper,
    "fullh4rd": FullH4rdScraper,
    "gezatek": GezatekScraper,
}

def get_supported_shops() -> List[Dict[str, str]]:
    return [{"id": k, "name": v.__name__.replace('Scraper', '').replace('_', ' ').title()} for k, v in SCRAPER_CLASSES.items()]

def validate_shop_id(shop_id: str) -> bool:
    return shop_id in SCRAPER_CLASSES

async def run_scraper(shop_id: str) -> List[Dict[str, Any]]:
    if shop_id not in SCRAPER_CLASSES:
        raise ValueError(f"Shop '{shop_id}' not supported")
    logger.info(f"Running scraper for {shop_id}")
    scraper = SCRAPER_CLASSES[shop_id]()
    return await scraper.run()

async def run_all_scrapers() -> Dict[str, List[Dict[str, Any]]]:
    results = {}
    for shop_id in SCRAPER_CLASSES:
        try:
            results[shop_id] = await run_scraper(shop_id)
        except Exception as e:
            logger.error(f"Error scraping {shop_id}: {e}")
            results[shop_id] = []
    return results
