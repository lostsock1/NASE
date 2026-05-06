import asyncio
import logging
import time
from decimal import Decimal, DecimalException
from typing import Optional

from models.constants import KNOWN_TOKENS
from models.types import Pair, PriceQuote, Token
from sources.base import Source
from util.config import SourceConfig

logger = logging.getLogger("nase")

USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
USDC_DECIMALS = 6


class JupiterSource(Source):
    name = "jupiter"

    def __init__(self, config: SourceConfig, api_key: Optional[str] = None):
        super().__init__(config, api_key)
        self._known_by_address = {t["address"]: t for t in KNOWN_TOKENS.get("solana", [])}

    async def _fetch_impl(self) -> list[PriceQuote]:
        quote_tokens = [
            token for token in KNOWN_TOKENS.get("solana", [])
            if token["address"] != USDC_MINT
        ]
        tasks = [self._quote_to_usdc(token) for token in quote_tokens]
        quotes: list[PriceQuote] = []
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, PriceQuote):
                quotes.append(result)
            elif isinstance(result, Exception):
                logger.warning("Jupiter quote failed: %s", str(result))
        return quotes

    async def _quote_to_usdc(self, token_info: dict[str, str]) -> PriceQuote | None:
        amount = self._quote_amount(token_info)
        params = {
            "inputMint": token_info["address"],
            "outputMint": USDC_MINT,
            "amount": str(amount),
        }
        headers = {"x-api-key": self.api_key} if self.api_key else None
        data = await self._get(f"{self.config.base_url}/swap/v1/quote", params=params, headers=headers)
        return self._normalize_quote(data, token_info)

    @staticmethod
    def _quote_amount(token_info: dict[str, str]) -> int:
        decimals = int(token_info.get("decimals", 0) or 0)
        symbol = token_info.get("symbol", "").upper()
        if symbol == "BONK" or decimals <= 5:
            multiplier = 1_000_000
        elif decimals <= 6:
            multiplier = 100
        else:
            multiplier = 10
        return (10 ** decimals) * multiplier

    def _normalize_quote(self, raw: dict, token_info: dict[str, str]) -> PriceQuote | None:
        try:
            out_amount = Decimal(str(raw.get("outAmount") or "0"))
            in_amount = Decimal(str(raw.get("inAmount") or (10 ** int(token_info.get("decimals", 0) or 0))))
            base_decimals = int(token_info.get("decimals", 0) or 0)
            if out_amount <= 0 or in_amount <= 0:
                return None
            base_units = in_amount / (Decimal(10) ** base_decimals)
            quote_units = out_amount / (Decimal(10) ** USDC_DECIMALS)
            price = quote_units / base_units
            if price <= 0:
                return None

            base = Token(
                address=token_info["address"],
                symbol=token_info.get("symbol", "???"),
                chain="solana",
                decimals=base_decimals,
            )
            quote = Token(address=USDC_MINT, symbol="USDC", chain="solana", decimals=USDC_DECIMALS)
            pair = Pair(base=base, quote=quote, pair_address=f"jupiter:{base.address}:{quote.address}")
            return PriceQuote(
                pair=pair,
                dex="Jupiter",
                source_api="jupiter",
                ask_price=price,
                bid_price=price,
                liquidity_usd=0.0,
                volume_24h_usd=0.0,
                fetched_at=time.time(),
            )
        except (KeyError, TypeError, ValueError, DecimalException):
            return None
