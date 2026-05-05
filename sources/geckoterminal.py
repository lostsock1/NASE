import asyncio
import logging
import time
from decimal import Decimal, DecimalException
from typing import Optional

from models.types import Token, Pair, PriceQuote
from sources.base import Source
from util.config import SourceConfig

logger = logging.getLogger("nase")

CHAIN_TO_GECKO_NETWORK: dict[str, str] = {
    "ethereum": "eth",
    "arbitrum": "arbitrum",
    "base": "base",
    "optimism": "optimism",
    "polygon": "polygon_pos",
    "bsc": "bsc",
    "avalanche": "avax",
    "solana": "solana",
    "hyperevm": "hyperevm",
    "zksync": "zksync",
    "linea": "linea",
}

MAX_PAGES_PER_CHAIN = 1


class GeckoTerminalSource(Source):
    name = "geckoterminal"

    def __init__(self, config: SourceConfig, chains: list[str] | None = None, api_key: Optional[str] = None):
        super().__init__(config, api_key)
        self._chains = chains or []
        self._seen_pairs: set[str] = set()

    async def _fetch_impl(self) -> list[PriceQuote]:
        self._seen_pairs.clear()
        chains = [chain for chain in self._chains if chain in CHAIN_TO_GECKO_NETWORK]
        if not chains:
            logger.warning("GeckoTerminal: no supported chains configured, skipping")
            return []

        quotes: list[PriceQuote] = []
        for chain in chains:
            for page in range(1, MAX_PAGES_PER_CHAIN + 1):
                if self.bucket_status["rate_limited"]:
                    logger.info("GeckoTerminal fetched %d total pools", len(quotes))
                    return quotes
                quotes.extend(await self._fetch_pools_page(chain, page))

        logger.info("GeckoTerminal fetched %d total pools", len(quotes))
        return quotes

    async def _fetch_pools_page(self, chain: str, page: int = 1) -> list[PriceQuote]:
        network = CHAIN_TO_GECKO_NETWORK[chain]
        url = f"{self.config.base_url}/api/v2/networks/{network}/pools"
        params = {"include": "base_token,quote_token,dex", "page": page}
        try:
            data = await self._get(url, params=params)
        except Exception:
            return []
        return self._normalize(data, chain)

    def _normalize(self, raw: dict, chain: str) -> list[PriceQuote]:
        included = self._included_by_id(raw.get("included", []))
        quotes: list[PriceQuote] = []
        now = time.time()

        for item in raw.get("data", []):
            try:
                attrs = item.get("attributes") or {}
                pair_addr = attrs.get("address") or self._pool_address_from_id(item.get("id", ""))
                if not pair_addr or pair_addr in self._seen_pairs:
                    continue
                self._seen_pairs.add(pair_addr)

                rel = item.get("relationships") or {}
                base = self._token_from_relationship(rel, included, "base_token", chain)
                quote = self._token_from_relationship(rel, included, "quote_token", chain)
                if not base.address or not quote.address:
                    continue

                price = Decimal(str(attrs.get("base_token_price_usd") or "0"))
                if price <= 0:
                    continue

                volume = attrs.get("volume_usd") or {}
                dex_id = (((rel.get("dex") or {}).get("data") or {}).get("id")) or "unknown"
                dex_name = included.get(dex_id, {}).get("attributes", {}).get("name") or dex_id

                quotes.append(
                    PriceQuote(
                        pair=Pair(base=base, quote=quote, pair_address=pair_addr),
                        dex=dex_name,
                        source_api="geckoterminal",
                        ask_price=price,
                        bid_price=price,
                        liquidity_usd=float(attrs.get("reserve_in_usd") or 0),
                        volume_24h_usd=float(volume.get("h24") or 0),
                        fetched_at=now,
                    )
                )
            except (KeyError, TypeError, ValueError, DecimalException, AttributeError):
                continue

        return quotes

    @staticmethod
    def _included_by_id(items: list[dict]) -> dict[str, dict]:
        return {item.get("id", ""): item for item in items if item.get("id")}

    @staticmethod
    def _pool_address_from_id(pool_id: str) -> str:
        if "_" not in pool_id:
            return pool_id
        return pool_id.split("_", 1)[1]

    @staticmethod
    def _token_from_relationship(rel: dict, included: dict[str, dict], key: str, chain: str) -> Token:
        token_id = (((rel.get(key) or {}).get("data") or {}).get("id")) or ""
        attrs = included.get(token_id, {}).get("attributes", {})
        address = attrs.get("address") or GeckoTerminalSource._pool_address_from_id(token_id)
        symbol = attrs.get("symbol") or "???"
        decimals = attrs.get("decimals") or 18
        return Token(address=address, symbol=symbol, chain=chain, decimals=int(decimals))
