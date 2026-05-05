import asyncio
import logging
import os
from typing import Optional

from models.types import PriceQuote
from sources.base import Source
from sources.quote_common import KYBER_CHAIN_NAMES, decimal_price_from_amounts, make_quote, quote_jobs, token_decimals, unit_amount
from util.config import SourceConfig

logger = logging.getLogger("nase")


class KyberSwapSource(Source):
    name = "kyberswap"

    def __init__(self, config: SourceConfig, chains: list[str] | None = None, api_key: Optional[str] = None):
        super().__init__(config, api_key)
        self._chains = chains or []
        self._client_id = os.getenv("KYBERSWAP_CLIENT_ID", "nase")

    async def _fetch_impl(self) -> list[PriceQuote]:
        jobs = [(chain, base, quote) for chain, base, quote in quote_jobs(self._chains) if chain in KYBER_CHAIN_NAMES]
        tasks = [self._quote(chain, base, quote) for chain, base, quote in jobs]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [r for r in results if isinstance(r, PriceQuote)]

    async def _quote(self, chain: str, base: dict[str, str], quote: dict[str, str]) -> PriceQuote | None:
        kyber_chain = KYBER_CHAIN_NAMES[chain]
        data = await self._get(
            f"{self.config.base_url}/{kyber_chain}/api/v1/routes",
            params={"tokenIn": base["address"], "tokenOut": quote["address"], "amountIn": unit_amount(base)},
            headers={"x-client-id": self._client_id},
        )
        return self._normalize(data, chain, base, quote)

    def _normalize(self, raw: dict, chain: str, base: dict[str, str], quote: dict[str, str]) -> PriceQuote | None:
        data = raw.get("data") or raw
        summary = data.get("routeSummary") or data
        out_amount = summary.get("amountOut") or summary.get("outputAmount")
        price = decimal_price_from_amounts(unit_amount(base), out_amount, token_decimals(base), token_decimals(quote))
        if price is None:
            return None
        return make_quote(source_api="kyberswap", dex="KyberSwap", chain=chain, base_info=base, quote_info=quote, price=price)
