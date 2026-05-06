import asyncio
import logging
import time
from decimal import Decimal, DecimalException
from typing import Optional

from sources.base import Source
from models.types import Token, Pair, PriceQuote
from models.constants import normalize_chain, KNOWN_TOKENS
from util.config import SourceConfig

logger = logging.getLogger("nase")


class DexScreenerSource(Source):
    name = "dexscreener"

    def __init__(self, config: SourceConfig, api_key: Optional[str] = None):
        super().__init__(config, api_key)
        self._seen_pairs: set[str] = set()

    async def _fetch_impl(self) -> list[PriceQuote]:
        self._seen_pairs.clear()
        quotes: list[PriceQuote] = []
        known = self._get_tokens_to_search()
        searches = [self._search_token(symbol) for symbol in known]
        results = await asyncio.gather(*searches, return_exceptions=True)
        for result in results:
            if isinstance(result, list):
                quotes.extend(result)
            elif isinstance(result, Exception):
                logger.warning("%s token search failed: %s", self.name, str(result))
        return quotes

    def _get_tokens_to_search(self) -> list[tuple[dict[str, str], str]]:
        pairs = []
        for chain, tokens in KNOWN_TOKENS.items():
            for token in tokens:
                pairs.append((token, chain))
        return pairs

    async def _search_token(self, info: tuple[dict[str, str], str]) -> list[PriceQuote]:
        token, chain = info
        url = f"{self.config.base_url}/latest/dex/search?q={token['symbol']}"
        try:
            data = await self._get(url)
        except Exception:
            return []
        return self._normalize(data, chain, token["address"])

    def _normalize(self, raw: dict, chain: str, target_address: str | None = None) -> list[PriceQuote]:
        quotes: list[PriceQuote] = []
        pairs = raw.get("pairs", [])
        if not isinstance(pairs, list):
            return quotes
        now = time.time()
        for p in pairs:
            try:
                pair_addr = p.get("pairAddress", "")
                if pair_addr in self._seen_pairs:
                    continue
                self._seen_pairs.add(pair_addr)

                pair_chain = normalize_chain(p.get("chainId", chain))
                if pair_chain != chain:
                    continue

                base_tok = p.get("baseToken", {})
                quote_tok = p.get("quoteToken", {})
                base_addr = base_tok.get("address", "")
                quote_addr = quote_tok.get("address", "")
                if target_address:
                    target = target_address.lower()
                    if base_addr.lower() != target and quote_addr.lower() != target:
                        continue

                base = Token(
                    address=base_addr,
                    symbol=base_tok.get("symbol", "???"),
                    chain=pair_chain,
                    decimals=0,
                )
                quote = Token(
                    address=quote_addr,
                    symbol=quote_tok.get("symbol", "???"),
                    chain=pair_chain,
                    decimals=0,
                )
                pair = Pair(base=base, quote=quote, pair_address=pair_addr)

                price_str = p.get("priceUsd", "0")
                if not price_str or price_str in ("", "0", "0.0"):
                    continue
                price = Decimal(str(price_str))

                quote_obj = PriceQuote(
                    pair=pair,
                    dex=p.get("dexId", "unknown"),
                    source_api="dexscreener",
                    ask_price=price,
                    bid_price=price,
                    liquidity_usd=float((p.get("liquidity") or {}).get("usd", 0) or 0),
                    volume_24h_usd=float((p.get("volume") or {}).get("h24", 0) or 0),
                    fetched_at=now,
                )
                quotes.append(quote_obj)
            except (KeyError, TypeError, DecimalException, AttributeError):
                continue
        return quotes
