import asyncio
import logging
import time
from decimal import Decimal, DecimalException
from typing import Optional

from models.types import Pair, PriceQuote, Token
from sources.base import Source
from sources.geckoterminal import CHAIN_TO_GECKO_NETWORK
from util.config import SourceConfig

logger = logging.getLogger("nase")

HYPERSWAP_CHAIN = "hyperevm"
MAX_PAGES = 3


class HyperSwapSource(Source):
    name = "hyperswap"

    def __init__(self, config: SourceConfig, api_key: Optional[str] = None):
        super().__init__(config, api_key)
        self._seen_pairs: set[str] = set()

    async def _fetch_impl(self) -> list[PriceQuote]:
        self._seen_pairs.clear()
        tasks = [self._fetch_pools_page(page) for page in range(1, MAX_PAGES + 1)]
        quotes: list[PriceQuote] = []
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, list):
                quotes.extend(result)
            elif isinstance(result, Exception):
                logger.warning("HyperSwap page fetch failed: %s", str(result))
        return quotes

    async def _fetch_pools_page(self, page: int) -> list[PriceQuote]:
        network = CHAIN_TO_GECKO_NETWORK[HYPERSWAP_CHAIN]
        url = f"{self.config.base_url}/api/v2/networks/{network}/pools"
        params = {"include": "base_token,quote_token,dex", "page": page}
        try:
            data = await self._get(url, params=params)
        except Exception:
            return []
        return self._normalize(data)

    def _normalize(self, raw: dict) -> list[PriceQuote]:
        included = {item.get("id", ""): item for item in raw.get("included", []) if item.get("id")}
        quotes: list[PriceQuote] = []
        now = time.time()
        for item in raw.get("data", []):
            try:
                rel = item.get("relationships") or {}
                dex_id = (((rel.get("dex") or {}).get("data") or {}).get("id")) or ""
                dex_name = included.get(dex_id, {}).get("attributes", {}).get("name") or dex_id
                if "hyperswap" not in f"{dex_id} {dex_name}".lower():
                    continue

                attrs = item.get("attributes") or {}
                pair_addr = attrs.get("address") or _address_from_id(item.get("id", ""))
                if not pair_addr or pair_addr in self._seen_pairs:
                    continue
                self._seen_pairs.add(pair_addr)

                base = _token_from_relationship(rel, included, "base_token")
                quote = _token_from_relationship(rel, included, "quote_token")
                price = Decimal(str(attrs.get("base_token_price_usd") or "0"))
                if not base.address or not quote.address or price <= 0:
                    continue
                volume = attrs.get("volume_usd") or {}
                quotes.append(
                    PriceQuote(
                        pair=Pair(base=base, quote=quote, pair_address=pair_addr),
                        dex=dex_name or "HyperSwap",
                        source_api="hyperswap",
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


def _address_from_id(raw_id: str) -> str:
    if "_" not in raw_id:
        return raw_id
    return raw_id.split("_", 1)[1]


def _token_from_relationship(rel: dict, included: dict[str, dict], key: str) -> Token:
    token_id = (((rel.get(key) or {}).get("data") or {}).get("id")) or ""
    attrs = included.get(token_id, {}).get("attributes", {})
    return Token(
        address=attrs.get("address") or _address_from_id(token_id),
        symbol=attrs.get("symbol") or "???",
        chain=HYPERSWAP_CHAIN,
        decimals=int(attrs.get("decimals") or 18),
    )
