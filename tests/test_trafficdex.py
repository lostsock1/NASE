from decimal import Decimal
import unittest

from sources.trafficdex import TrafficDexSource
from util.config import SourceConfig


class TrafficDexSourceTests(unittest.TestCase):
    def test_normalize_keeps_high_traffic_dexes_only(self):
        src = TrafficDexSource(SourceConfig(True, "https://api.geckoterminal.com", 1, 1, 30), ["ethereum"])
        raw = {
            "data": [
                {
                    "id": "eth_0xpool",
                    "attributes": {
                        "address": "0xpool",
                        "base_token_price_usd": "2500",
                        "reserve_in_usd": "123456",
                        "volume_usd": {"h24": "999"},
                    },
                    "relationships": {
                        "base_token": {"data": {"id": "eth_0xbase"}},
                        "quote_token": {"data": {"id": "eth_0xquote"}},
                        "dex": {"data": {"id": "uniswap-v3"}},
                    },
                },
                {
                    "id": "eth_0xignored",
                    "attributes": {"address": "0xignored", "base_token_price_usd": "1"},
                    "relationships": {"dex": {"data": {"id": "tiny-dex"}}},
                },
            ],
            "included": [
                {"id": "eth_0xbase", "attributes": {"address": "0xbase", "symbol": "WETH", "decimals": 18}},
                {"id": "eth_0xquote", "attributes": {"address": "0xquote", "symbol": "USDC", "decimals": 6}},
                {"id": "uniswap-v3", "attributes": {"name": "Uniswap V3"}},
                {"id": "tiny-dex", "attributes": {"name": "Tiny Dex"}},
            ],
        }

        quotes = src._normalize(raw, "ethereum")

        self.assertEqual(len(quotes), 1)
        self.assertEqual(quotes[0].dex, "Uniswap:Uniswap V3")
        self.assertEqual(quotes[0].ask_price, Decimal("2500"))
        self.assertEqual(quotes[0].source_api, "trafficdex")


if __name__ == "__main__":
    unittest.main()
