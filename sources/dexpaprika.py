import logging
from typing import Optional

from sources.base import Source
from models.types import PriceQuote
from util.config import SourceConfig

logger = logging.getLogger("nase")


class DexPaprikaSource(Source):
    name = "dexpaprika"

    def __init__(self, config: SourceConfig, api_key: Optional[str] = None):
        super().__init__(config, api_key)
        self._seen_pairs: set[str] = set()

    async def _fetch_impl(self) -> list[PriceQuote]:
        self._seen_pairs.clear()
        return []

    async def _fetch_pools_page(self, chain: str, page: int = 0, limit: int = 100) -> list[PriceQuote]:
        url = f"{self.config.base_url}/networks/{chain}/pools"
        params = {"page": page, "limit": limit}
        try:
            data = await self._get(url, params=params)
        except Exception:
            return []
        return self._normalize_pools(data.get("pools", []), chain)

    def _normalize_pools(self, pools: list[dict], chain: str) -> list[PriceQuote]:
        return []
