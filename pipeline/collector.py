import asyncio
import logging

from sources.base import Source
from models.types import PriceQuote
from util.config import Config

logger = logging.getLogger("nase")


class Collector:
    def __init__(self, config: Config):
        self.config = config
        self._sources: list[Source] = []

    def register(self, source: Source) -> None:
        self._sources.append(source)

    @property
    def source_statuses(self) -> dict[str, dict]:
        statuses = {}
        for src in self._sources:
            bs = src.bucket_status
            statuses[src.name] = {
                "healthy": src.healthy,
                "rate_limited": bs["rate_limited"],
                "rate_wait_seconds": bs["time_until_next"],
                "consecutive_429s": bs["consecutive_429s"],
                "total_429s": bs["total_429s"],
                "success_rate": bs["success_rate"],
            }
        return statuses

    async def start_all(self) -> None:
        tasks = [src.start() for src in self._sources]
        await asyncio.gather(*tasks)

    async def stop_all(self) -> None:
        tasks = [src.stop() for src in self._sources]
        await asyncio.gather(*tasks)

    async def collect(self) -> dict[str, list[PriceQuote]]:
        tasks = [src.fetch() for src in self._sources]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        output: dict[str, list[PriceQuote]] = {}
        for source, result in zip(self._sources, results):
            if isinstance(result, Exception):
                logger.error("%s: %s", source.name, str(result))
                output[source.name] = []
            else:
                output[source.name] = result
        return output
