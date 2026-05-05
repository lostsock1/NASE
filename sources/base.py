from abc import ABC, abstractmethod
import asyncio
import logging
from typing import Optional

import aiohttp

from models.types import PriceQuote
from util.config import SourceConfig
from util.rate_limiter import TokenBucket

logger = logging.getLogger("nase")


class Source(ABC):
    name: str

    def __init__(self, config: SourceConfig, api_key: Optional[str] = None):
        self.config = config
        self.api_key = api_key
        self._bucket = TokenBucket(rate=config.max_rps, burst=config.max_concurrent)
        self._semaphore = asyncio.Semaphore(config.max_concurrent)
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def healthy(self) -> bool:
        status = self._bucket.status
        return not status["rate_limited"] and not status.get("circuit_open", False)

    @property
    def bucket_status(self) -> dict:
        """Full telemetry from the rate limiter (for TUI display)."""
        return self._bucket.status

    async def start(self) -> None:
        connector = aiohttp.TCPConnector(
            limit=self.config.max_concurrent,
            enable_cleanup_closed=True,
            ttl_dns_cache=300,
            force_close=False,
        )
        timeout = aiohttp.ClientTimeout(total=self.config.timeout_seconds)
        self._session = aiohttp.ClientSession(connector=connector, timeout=timeout)

    async def stop(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    async def fetch(self) -> list[PriceQuote]:
        if not self._session:
            raise RuntimeError(f"Source {self.name} not started")

        if self._bucket.status["rate_limited"]:
            wait = self._bucket.status["time_until_next"]
            logger.warning(
                "Source %s in backoff %.1fs (429#%d)",
                self.name, wait, self._bucket.status["consecutive_429s"],
                extra={"source": self.name},
            )
            return []

        try:
            results = await asyncio.wait_for(self._fetch_impl(), timeout=self.config.timeout_seconds)
            logger.info(
                "Source %s fetched %d pairs",
                self.name,
                len(results),
                extra={"source": self.name, "pairs": len(results)},
            )
            return results
        except asyncio.TimeoutError:
            logger.error(
                "Source %s timed out after %ss",
                self.name,
                self.config.timeout_seconds,
                extra={"source": self.name},
            )
            return []
        except RateLimitedError:
            logger.warning(
                "Source %s 429 backoff %.0fs",
                self.name,
                self._bucket.status["current_delay"],
                extra={"source": self.name},
            )
            return []
        except Exception as e:
            logger.error(
                "Source %s failed: %s",
                self.name,
                str(e),
                extra={"source": self.name},
            )
            return []

    async def _get(self, url: str, **kwargs) -> dict:
        """HTTP GET with bucket pacing and 429 backoff integration."""
        await self._bucket.acquire()
        async with self._semaphore:
            async with self._session.get(url, **kwargs) as resp:
                if resp.status == 429:
                    retry = self._parse_retry_after(resp.headers)
                    self._bucket.handle_429(retry)
                    logger.warning(
                        "Source %s 429: retry-after=%s, backoff=%.0fs (429#%d)",
                        self.name, retry, self._bucket.status["current_delay"],
                        self._bucket.status["consecutive_429s"],
                        extra={"source": self.name, "status": 429},
                    )
                    raise RateLimitedError("Rate limited")
                resp.raise_for_status()
                self._bucket.handle_success()
                return await resp.json()

    async def _post(self, url: str, json_data: dict, **kwargs) -> dict:
        """HTTP POST with bucket pacing and 429 backoff integration."""
        await self._bucket.acquire()
        async with self._semaphore:
            async with self._session.post(url, json=json_data, **kwargs) as resp:
                if resp.status == 429:
                    retry = self._parse_retry_after(resp.headers)
                    self._bucket.handle_429(retry)
                    logger.warning(
                        "Source %s 429: retry-after=%s, backoff=%.0fs (429#%d)",
                        self.name, retry, self._bucket.status["current_delay"],
                        self._bucket.status["consecutive_429s"],
                        extra={"source": self.name, "status": 429},
                    )
                    raise RateLimitedError("Rate limited")
                resp.raise_for_status()
                self._bucket.handle_success()
                return await resp.json()

    @staticmethod
    def _parse_retry_after(headers) -> float | None:
        """Extract Retry-After header as seconds (NASE3 pattern)."""
        val = headers.get("Retry-After") or headers.get("retry-after")
        if val is None:
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    @abstractmethod
    async def _fetch_impl(self) -> list[PriceQuote]:
        ...


class RateLimitedError(Exception):
    pass
