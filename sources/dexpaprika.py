import asyncio
import logging
import time
from decimal import Decimal, DecimalException
from typing import Optional

from sources.base import Source
from models.types import Token, Pair, PriceQuote
from models.constants import normalize_chain
from util.config import SourceConfig

logger = logging.getLogger("nase")

MAX_PAGES_PER_CHAIN = 3
POOLS_PER_PAGE = 100


class DexPaprikaSource(Source):
    name = "dexpaprika"

    def __init__(self, config: SourceConfig, chains: list[str] | None = None, api_key: Optional[str] = None):
        super().__init__(config, api_key)
        self._chains = chains or []
        self._seen_pairs: set[str] = set()

    async def _fetch_impl(self) -> list[PriceQuote]:
        self._seen_pairs.clear()
        if not self._chains:
            logger.warning("DexPaprika: no chains configured, skipping")
            return []

        quotes: list[PriceQuote] = []
        tasks = []
        for chain in self._chains:
            for page in range(MAX_PAGES_PER_CHAIN):
                tasks.append(self._fetch_pools_page(chain, page, POOLS_PER_PAGE))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, list):
                quotes.extend(result)
            elif isinstance(result, Exception):
                logger.warning("DexPaprika page fetch failed: %s", str(result))

        logger.info("DexPaprika fetched %d total pools", len(quotes))
        return quotes

    async def _fetch_pools_page(self, chain: str, page: int = 0, limit: int = 100) -> list[PriceQuote]:
        url = f"{self.config.base_url}/networks/{chain}/pools"
        params = {"page": page, "limit": limit}
        try:
            data = await self._get(url, params=params)
        except Exception:
            return []
        return self._normalize_pools(data.get("pools", []), chain)

    def _normalize_pools(self, pools: list[dict], chain: str) -> list[PriceQuote]:
        quotes: list[PriceQuote] = []
        now = time.time()

        for p in pools:
            try:
                pool_addr = p.get("id", "")
                if not pool_addr:
                    continue
                if pool_addr in self._seen_pairs:
                    continue
                self._seen_pairs.add(pool_addr)

                tokens = p.get("tokens")
                if not tokens or not isinstance(tokens, list) or len(tokens) < 2:
                    continue

                tok0 = tokens[0]
                tok1 = tokens[1]

                base = Token(
                    address=tok0.get("id", ""),
                    symbol=tok0.get("symbol", "???"),
                    chain=normalize_chain(p.get("chain", chain)),
                    decimals=tok0.get("decimals", 18),
                )
                quote = Token(
                    address=tok1.get("id", ""),
                    symbol=tok1.get("symbol", "???"),
                    chain=normalize_chain(p.get("chain", chain)),
                    decimals=tok1.get("decimals", 18),
                )
                pair = Pair(base=base, quote=quote, pair_address=pool_addr)

                price_val = p.get("price_usd")
                if price_val is None:
                    continue
                price = Decimal(str(price_val))
                if price <= 0:
                    continue

                quote_obj = PriceQuote(
                    pair=pair,
                    dex=p.get("dex_name", p.get("dex_id", "unknown")),
                    source_api="dexpaprika",
                    ask_price=price,
                    bid_price=price,
                    liquidity_usd=0.0,  # API does not expose per-pool liquidity
                    volume_24h_usd=float(p.get("volume_usd", 0) or 0),
                    fetched_at=now,
                )
                quotes.append(quote_obj)

            except (KeyError, TypeError, DecimalException):
                continue

        return quotes
