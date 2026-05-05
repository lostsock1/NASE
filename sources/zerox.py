import asyncio
import logging
import os
from typing import Optional

from models.types import PriceQuote
from sources.base import Source
from sources.quote_common import CHAIN_IDS, collect_quote_jobs, decimal_price_from_amounts, token_decimals, unit_amount
from util.config import SourceConfig

logger = logging.getLogger("nase")


class ZeroXSource(Source):
    name = "zerox"

    def __init__(self, config: SourceConfig, chains: list[str] | None = None, api_key: Optional[str] = None):
        super().__init__(config, api_key)
        self._chains = chains or []
        self._taker = os.getenv("ZEROX_TAKER_ADDRESS")

    async def _fetch_impl(self) -> list[PriceQuote]:
        if not self.api_key or not self._taker:
            logger.warning("0x: ZEROX_API_KEY and ZEROX_TAKER_ADDRESS required, skipping")
            return []
        return await collect_quote_jobs(self, self._chains, self._quote)

    async def _quote(self, chain: str, base: dict[str, str], quote: dict[str, str], amount_raw: str | None = None) -> PriceQuote | None:
        data = await self._get(
            f"{self.config.base_url}/swap/allowance-holder/price",
            params={
                "chainId": str(CHAIN_IDS[chain]),
                "sellToken": base["address"],
                "buyToken": quote["address"],
                "sellAmount": amount_raw or unit_amount(base),
                "taker": self._taker,
            },
            headers={"0x-api-key": self.api_key, "0x-version": "v2"},
        )
        return self._normalize(data, chain, base, quote, amount_raw or unit_amount(base))

    def _normalize(self, raw: dict, chain: str, base: dict[str, str], quote: dict[str, str], in_amount_raw: str | None = None) -> PriceQuote | None:
        out_amount = raw.get("buyAmount")
        price = decimal_price_from_amounts(in_amount_raw or unit_amount(base), out_amount, token_decimals(base), token_decimals(quote))
        if price is None:
            return None
        from sources.quote_common import make_quote
        return make_quote(source_api="zerox", dex="0x", chain=chain, base_info=base, quote_info=quote, price=price)
