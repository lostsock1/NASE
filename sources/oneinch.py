import asyncio
import logging
from typing import Optional

from models.types import PriceQuote
from sources.base import Source
from sources.quote_common import CHAIN_IDS, collect_quote_jobs, decimal_price_from_amounts, token_decimals, unit_amount
from util.config import SourceConfig

logger = logging.getLogger("nase")


class OneInchSource(Source):
    name = "oneinch"

    def __init__(self, config: SourceConfig, chains: list[str] | None = None, api_key: Optional[str] = None):
        super().__init__(config, api_key)
        self._chains = chains or []

    async def _fetch_impl(self) -> list[PriceQuote]:
        if not self.api_key:
            logger.warning("1inch: ONEINCH_API_KEY required, skipping")
            return []
        return await collect_quote_jobs(self, self._chains, self._quote)

    async def _quote(self, chain: str, base: dict[str, str], quote: dict[str, str], amount_raw: str | None = None) -> PriceQuote | None:
        data = await self._get(
            f"{self.config.base_url}/{CHAIN_IDS[chain]}/quote",
            params={"src": base["address"], "dst": quote["address"], "amount": amount_raw or unit_amount(base)},
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        return self._normalize(data, chain, base, quote, amount_raw or unit_amount(base))

    def _normalize(self, raw: dict, chain: str, base: dict[str, str], quote: dict[str, str], in_amount_raw: str | None = None) -> PriceQuote | None:
        out_amount = raw.get("dstAmount")
        price = decimal_price_from_amounts(in_amount_raw or unit_amount(base), out_amount, token_decimals(base), token_decimals(quote))
        if price is None:
            return None
        from sources.quote_common import make_quote
        return make_quote(source_api="oneinch", dex="1inch", chain=chain, base_info=base, quote_info=quote, price=price)
