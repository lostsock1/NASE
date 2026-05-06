import asyncio
import unittest

from models.types import PriceQuote
from sources.base import Source
from util.config import SourceConfig


class TimeoutSource(Source):
    name = "timeout_source"

    async def _fetch_impl(self) -> list[PriceQuote]:
        await asyncio.sleep(0.05)
        return []


class HealthySource(Source):
    name = "healthy_source"

    async def _fetch_impl(self) -> list[PriceQuote]:
        return []


class SourceHealthTests(unittest.IsolatedAsyncioTestCase):
    async def test_timeout_marks_source_unhealthy(self):
        source = TimeoutSource(
            SourceConfig(
                enabled=True,
                base_url="http://example.test",
                max_rps=10,
                max_concurrent=1,
                timeout_seconds=0,
            )
        )
        source._session = object()

        result = await source.fetch()

        self.assertEqual(result, [])
        self.assertFalse(source.healthy)
        self.assertEqual(source.failure_status["consecutive_failures"], 1)
        self.assertEqual(source.failure_status["last_error"], "timeout after 0s")

    async def test_success_clears_previous_failure(self):
        source = HealthySource(
            SourceConfig(
                enabled=True,
                base_url="http://example.test",
                max_rps=10,
                max_concurrent=1,
                timeout_seconds=1,
            )
        )
        source._session = object()
        source._record_failure("old failure")

        result = await source.fetch()

        self.assertEqual(result, [])
        self.assertTrue(source.healthy)
        self.assertEqual(source.failure_status["consecutive_failures"], 0)
        self.assertIsNone(source.failure_status["last_error"])


if __name__ == "__main__":
    unittest.main()
