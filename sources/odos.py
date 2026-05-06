import asyncio
import logging
from typing import Optional

from models.types import PriceQuote
from sources.base import Source
from sources.quote_common import CHAIN_IDS, QUOTE_USER_ADDRESS, collect_quote_jobs, decimal_price_from_amounts, make_quote, token_decimals, unit_amount
from util.config import SourceConfig

logger = logging.getLogger("nase")


class OdosSource(Source):
    name = "odos"

    def __init__(self, config: SourceConfig, chains: list[str] | None = None, api_key: Optional[str] = None):
        super().__init__(config, api_key)
        self._chains = chains or []

    async def _fetch_impl(self) -> list[PriceQuote]:
        return await collect_quote_jobs(self, self._chains, self._quote)

    async def _quote(self, chain: str, base: dict[str, str], quote: dict[str, str], amount_raw: str | None = None) -> PriceQuote | None:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        data = await self._post(
            f"{self.config.base_url}/sor/quote/v2",
            json_data={
                "chainId": CHAIN_IDS[chain],
                "inputTokens": [{"tokenAddress": base["address"], "amount": amount_raw or unit_amount(base)}],
                "outputTokens": [{"tokenAddress": quote["address"], "proportion": 1}],
                "userAddr": QUOTE_USER_ADDRESS,
                "slippageLimitPercent": 1,
                "disableRFQs": True,
            },
            headers=headers,
        )
        return self._normalize(data, chain, base, quote, amount_raw or unit_amount(base))

    def _normalize(self, raw: dict, chain: str, base: dict[str, str], quote: dict[str, str], in_amount_raw: str | None = None) -> PriceQuote | None:
        out_amounts = raw.get("outAmounts") or []
        out_amount = out_amounts[0] if out_amounts else raw.get("outAmount")
        price = decimal_price_from_amounts(in_amount_raw or unit_amount(base), out_amount, token_decimals(base), token_decimals(quote))
        if price is None:
            return None
        return make_quote(source_api="odos", dex="Odos", chain=chain, base_info=base, quote_info=quote, price=price)
