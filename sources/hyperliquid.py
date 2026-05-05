import logging
import time
from decimal import Decimal, DecimalException
from typing import Optional

from models.types import Pair, PriceQuote, Token
from sources.base import Source
from util.config import SourceConfig

logger = logging.getLogger("nase")


class HyperliquidSource(Source):
    name = "hyperliquid"

    def __init__(self, config: SourceConfig, api_key: Optional[str] = None):
        super().__init__(config, api_key)

    async def _fetch_impl(self) -> list[PriceQuote]:
        data = await self._post(f"{self.config.base_url}/info", {"type": "spotMetaAndAssetCtxs"})
        return self._normalize(data)

    def _normalize(self, raw) -> list[PriceQuote]:
        if not isinstance(raw, list) or len(raw) < 2:
            return []
        meta = raw[0] or {}
        contexts = raw[1] or []
        tokens = {t.get("index"): t for t in meta.get("tokens", []) if t.get("index") is not None}
        quotes: list[PriceQuote] = []
        now = time.time()

        for market, ctx in zip(meta.get("universe", []), contexts):
            try:
                token_indexes = market.get("tokens") or []
                if len(token_indexes) < 2:
                    continue
                base_meta = tokens.get(token_indexes[0], {})
                quote_meta = tokens.get(token_indexes[1], {})
                price_val = ctx.get("midPx") or ctx.get("markPx") or ctx.get("prevDayPx")
                if price_val is None:
                    continue
                price = Decimal(str(price_val))
                if price <= 0:
                    continue

                base_symbol = base_meta.get("name") or market.get("name", "???").split("/")[0]
                quote_symbol = quote_meta.get("name") or "USDC"
                base = Token(
                    address=f"hyperliquid{token_indexes[0]}",
                    symbol=base_symbol,
                    chain="hyperliquid",
                    decimals=int(base_meta.get("szDecimals") or base_meta.get("weiDecimals") or 0),
                )
                quote = Token(
                    address=f"hyperliquid{token_indexes[1]}",
                    symbol=quote_symbol,
                    chain="hyperliquid",
                    decimals=int(quote_meta.get("szDecimals") or quote_meta.get("weiDecimals") or 0),
                )
                pair = Pair(
                    base=base,
                    quote=quote,
                    pair_address=f"hyperliquid:{market.get('index', market.get('name', base_symbol))}",
                )
                quotes.append(
                    PriceQuote(
                        pair=pair,
                        dex="Hyperliquid Spot",
                        source_api="hyperliquid",
                        ask_price=price,
                        bid_price=price,
                        liquidity_usd=0.0,
                        volume_24h_usd=float(ctx.get("dayNtlVlm") or 0),
                        fetched_at=now,
                    )
                )
            except (KeyError, TypeError, ValueError, DecimalException, AttributeError):
                continue
        return quotes
