import logging
from typing import Optional

from sources.base import Source
from models.types import PriceQuote
from util.config import SourceConfig

logger = logging.getLogger("nase")


class SwapApiSource(Source):
    name = "swapapi"

    def __init__(self, config: SourceConfig, api_key: Optional[str] = None):
        super().__init__(config, api_key)

    async def _fetch_impl(self) -> list[PriceQuote]:
        if not self.api_key:
            logger.warning("SwapAPI: no API key configured, skipping")
            return []
        return []

    def _normalize_price(self, token_info: dict, chain: str) -> list[PriceQuote]:
        return []
