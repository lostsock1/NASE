import asyncio
import logging
from typing import Optional

from models.types import PriceQuote
from sources.base import Source
from sources.quote_common import CHAIN_IDS, collect_quote_jobs, decimal_price_from_amounts, make_quote, token_decimals, unit_amount
from util.config import SourceConfig

logger = logging.getLogger("nase")


class VeloraSource(Source):
    name = "velora"

    def __init__(self, config: SourceConfig, chains: list[str] | None = None, api_key: Optional[str] = None):
        super().__init__(config, api_key)
        self._chains = chains or []

    async def _fetch_impl(self) -> list[PriceQuote]:
        return await collect_quote_jobs(self, self._chains, self._quote)

    async def _quote(self, chain: str, base: dict[str, str], quote: dict[str, str], amount_raw: str | None = None) -> PriceQuote | None:
        data = await self._get(
            f"{self.config.base_url}/prices",
            params={
                "srcToken": base["address"],
                "srcDecimals": str(token_decimals(base)),
                "destToken": quote["address"],
                "destDecimals": str(token_decimals(quote)),
                "amount": amount_raw or unit_amount(base),
                "side": "SELL",
                "network": str(CHAIN_IDS[chain]),
            },
        )
        return self._normalize(data, chain, base, quote, amount_raw or unit_amount(base))

    def _normalize(self, raw: dict, chain: str, base: dict[str, str], quote: dict[str, str], in_amount_raw: str | None = None) -> PriceQuote | None:
        route = raw.get("priceRoute") or raw
        out_amount = route.get("destAmount") or route.get("outAmount")
        price = decimal_price_from_amounts(in_amount_raw or unit_amount(base), out_amount, token_decimals(base), token_decimals(quote))
        if price is None:
            return None
        dex = route.get("contractMethod") or "Velora"
        return make_quote(source_api="velora", dex=f"Velora:{dex}", chain=chain, base_info=base, quote_info=quote, price=price)
