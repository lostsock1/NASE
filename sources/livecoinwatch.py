import logging
from typing import Optional

import aiohttp

from util.config import SourceConfig

logger = logging.getLogger("nase")


class LiveCoinWatchClient:
    """Standalone client for LiveCoinWatch reference price data.

    Fetches aggregated coin rates/volume/cap via POST to /coins/list.
    Not a pipeline Source — does not produce PriceQuote objects.
    """

    def __init__(self, config: SourceConfig, api_key: Optional[str] = None):
        self.config = config
        self.api_key = api_key
        self._session: Optional[aiohttp.ClientSession] = None

    async def start(self) -> None:
        connector = aiohttp.TCPConnector(limit=1, ttl_dns_cache=300)
        timeout = aiohttp.ClientTimeout(total=self.config.timeout_seconds)
        self._session = aiohttp.ClientSession(connector=connector, timeout=timeout)

    async def stop(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    async def fetch_rates(self, limit: int = 200) -> list[dict]:
        """Fetch top coins by rank. Returns list of {code, rate, volume, cap, delta}."""
        if not self._session:
            return []
        if not self.api_key:
            logger.warning("LiveCoinWatch: no API key configured, skipping")
            return []

        url = f"{self.config.base_url}/coins/list"
        payload = {
            "currency": "USD",
            "sort": "rank",
            "order": "ascending",
            "offset": 0,
            "limit": min(limit, 100),
            "meta": False,
        }
        headers = {
            "content-type": "application/json",
            "x-api-key": self.api_key,
        }
        try:
            async with self._session.post(url, json=payload, headers=headers) as resp:
                if resp.status == 429:
                    logger.warning("LiveCoinWatch: 429 rate limited")
                    return []
                resp.raise_for_status()
                data = await resp.json()
                logger.info("LiveCoinWatch: fetched %d coin rates", len(data))
                return data
        except Exception as e:
            logger.warning("LiveCoinWatch fetch failed: %s", str(e))
            return []
