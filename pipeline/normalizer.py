import logging
import time

from models.types import PriceQuote
from util.config import Config

logger = logging.getLogger("nase")


POOL_SOURCES = {"dexscreener", "dexpaprika", "geckoterminal", "hyperswap", "trafficdex"}
EXECUTABLE_SOURCES = {"lifi", "openocean", "velora", "odos", "kyberswap", "zerox", "oneinch"}
STABLE_SYMBOLS = {"USDC", "USDT", "USDBC", "DAI", "USDE", "USD0"}
MIN_POOL_LIQUIDITY_USD = 10_000
MIN_POOL_VOLUME_24H_USD = 500
STABLE_MIN_PRICE = 0.97
STABLE_MAX_PRICE = 1.03


class Normalizer:
    def __init__(self, config: Config):
        self.config = config
        self._max_age = max(config.refresh_interval_seconds * 6, 120)
        self._chains = set(config.chains)

    def normalize_all(self, raw_data: dict[str, list[PriceQuote]]) -> list[PriceQuote]:
        all_quotes: list[PriceQuote] = []
        now = time.time()

        for source_name, quotes in raw_data.items():
            for q in quotes:
                if q.pair.chain not in self._chains:
                    continue
                if q.ask_price <= 0 or q.bid_price <= 0:
                    continue
                if now - q.fetched_at > self._max_age:
                    continue
                if q.source_api in POOL_SOURCES and not self._has_enough_market_activity(q):
                    continue
                if q.source_api in EXECUTABLE_SOURCES and not q.executable:
                    continue
                if self._is_stable_pair(q) and not (STABLE_MIN_PRICE <= float(q.mid_price) <= STABLE_MAX_PRICE):
                    continue
                if not self._is_valid_address(q.pair.base.address):
                    continue
                if not self._is_valid_address(q.pair.quote.address):
                    continue
                all_quotes.append(q)

        logger.info("Normalized %d total quotes from %d sources", len(all_quotes), len(raw_data))
        return all_quotes

    @staticmethod
    def _is_stable_pair(q: PriceQuote) -> bool:
        return q.pair.base.symbol.upper() in STABLE_SYMBOLS and q.pair.quote.symbol.upper() in STABLE_SYMBOLS

    @staticmethod
    def _has_enough_market_activity(q: PriceQuote) -> bool:
        if q.liquidity_usd <= 0:
            return q.volume_24h_usd >= MIN_POOL_VOLUME_24H_USD
        return q.liquidity_usd >= MIN_POOL_LIQUIDITY_USD and q.volume_24h_usd >= MIN_POOL_VOLUME_24H_USD

    @staticmethod
    def _is_valid_address(addr: str) -> bool:
        if not addr or len(addr) < 10:
            return False
        return addr.startswith("0x") or addr.isalnum()
