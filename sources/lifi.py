import asyncio
import logging
import os
from typing import Optional

from models.types import PriceQuote
from sources.base import Source
from sources.quote_common import CHAIN_IDS, QUOTE_USER_ADDRESS, decimal_price_from_amounts, quote_jobs, token_decimals, unit_amount
from util.config import SourceConfig

logger = logging.getLogger("nase")


class LifiSource(Source):
    name = "lifi"

    def __init__(self, config: SourceConfig, chains: list[str] | None = None, api_key: Optional[str] = None):
        super().__init__(config, api_key)
        self._chains = chains or []
        self._from_address = os.getenv("LIFI_FROM_ADDRESS", QUOTE_USER_ADDRESS)

    async def _fetch_impl(self) -> list[PriceQuote]:
        tasks = [self._quote(chain, base, quote) for chain, base, quote in quote_jobs(self._chains)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [r for r in results if isinstance(r, PriceQuote)]

    async def _quote(self, chain: str, base: dict[str, str], quote: dict[str, str]) -> PriceQuote | None:
        headers = {"x-lifi-api-key": self.api_key} if self.api_key else None
        data = await self._get(
            f"{self.config.base_url}/quote",
            params={
                "fromChain": str(CHAIN_IDS[chain]),
                "toChain": str(CHAIN_IDS[chain]),
                "fromToken": base["address"],
                "toToken": quote["address"],
                "fromAmount": unit_amount(base),
                "fromAddress": self._from_address,
            },
            headers=headers,
        )
        return self._normalize(data, chain, base, quote)

    def _normalize(self, raw: dict, chain: str, base: dict[str, str], quote: dict[str, str]) -> PriceQuote | None:
        estimate = raw.get("estimate") or {}
        out_amount = estimate.get("toAmount") or raw.get("toAmount")
        price = decimal_price_from_amounts(unit_amount(base), out_amount, token_decimals(base), token_decimals(quote))
        if price is None:
            return None
        tool = raw.get("tool") or raw.get("toolDetails", {}).get("name") or "LI.FI"
        from sources.quote_common import make_quote
        return make_quote(source_api="lifi", dex=f"LI.FI:{tool}", chain=chain, base_info=base, quote_info=quote, price=price)
