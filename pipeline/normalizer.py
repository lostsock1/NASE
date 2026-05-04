import logging
import time

from models.types import PriceQuote
from util.config import Config

logger = logging.getLogger("nase")


class Normalizer:
    def __init__(self, config: Config):
        self.config = config
        self._max_age = config.refresh_interval_seconds * 2

    def normalize_all(self, raw_data: dict[str, list[PriceQuote]]) -> list[PriceQuote]:
        all_quotes: list[PriceQuote] = []
        now = time.time()

        for source_name, quotes in raw_data.items():
            for q in quotes:
                if q.ask_price <= 0 or q.bid_price <= 0:
                    continue
                if now - q.fetched_at > self._max_age:
                    continue
                if not self._is_valid_address(q.pair.base.address):
                    continue
                if not self._is_valid_address(q.pair.quote.address):
                    continue
                all_quotes.append(q)

        logger.info("Normalized %d total quotes from %d sources", len(all_quotes), len(raw_data))
        return all_quotes

    @staticmethod
    def _is_valid_address(addr: str) -> bool:
        if not addr or len(addr) < 10:
            return False
        return addr.startswith("0x") or addr.isalnum()
