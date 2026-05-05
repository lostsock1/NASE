import asyncio
import unittest

from sources.base import Source
from util.config import SourceConfig


class SlowSource(Source):
    name = "slow"

    async def _fetch_impl(self):
        await asyncio.sleep(0.05)
        return [object()]


class SourceTimeoutTests(unittest.TestCase):
    def test_fetch_timeout_returns_empty_list(self):
        async def run():
            source = SlowSource(SourceConfig(True, "https://example.test", 1, 1, 0.01))
            source._session = object()
            return await source.fetch()

        self.assertEqual(asyncio.run(run()), [])


if __name__ == "__main__":
    unittest.main()
