from decimal import Decimal
import unittest

from sources.hyperliquid import HyperliquidSource
from sources.hyperswap import HyperSwapSource
from util.config import SourceConfig


class HyperliquidSourceTests(unittest.TestCase):
    def test_normalize_spot_meta_and_contexts(self):
        src = HyperliquidSource(SourceConfig(True, "https://api.hyperliquid.xyz", 1, 1, 15))
        raw = [
            {
                "tokens": [
                    {"index": 0, "name": "PURR", "szDecimals": 0, "weiDecimals": 5},
                    {"index": 1, "name": "USDC", "szDecimals": 0, "weiDecimals": 6},
                ],
                "universe": [{"name": "PURR/USDC", "tokens": [0, 1], "index": 7}],
            },
            [{"midPx": "0.42", "dayNtlVlm": "12345"}],
        ]

        quotes = src._normalize(raw)

        self.assertEqual(len(quotes), 1)
        self.assertEqual(quotes[0].pair.base.symbol, "PURR")
        self.assertEqual(quotes[0].ask_price, Decimal("0.42"))
        self.assertEqual(quotes[0].volume_24h_usd, 12345.0)


class HyperSwapSourceTests(unittest.TestCase):
    def test_normalize_filters_hyperswap_pools(self):
        src = HyperSwapSource(SourceConfig(True, "https://api.geckoterminal.com", 1, 1, 20))
        raw = {
            "data": [
                {
                    "id": "hyperevm_0xpool",
                    "attributes": {
                        "address": "0xpool",
                        "base_token_price_usd": "2.50",
                        "reserve_in_usd": "1000",
                        "volume_usd": {"h24": "500"},
                    },
                    "relationships": {
                        "base_token": {"data": {"id": "hyperevm_0xbase"}},
                        "quote_token": {"data": {"id": "hyperevm_0xquote"}},
                        "dex": {"data": {"id": "hyperswap-v3"}},
                    },
                },
                {
                    "id": "hyperevm_0xother",
                    "attributes": {"address": "0xother", "base_token_price_usd": "9"},
                    "relationships": {"dex": {"data": {"id": "otherdex"}}},
                },
            ],
            "included": [
                {"id": "hyperevm_0xbase", "attributes": {"address": "0xbase", "symbol": "HYPE", "decimals": 18}},
                {"id": "hyperevm_0xquote", "attributes": {"address": "0xquote", "symbol": "USDC", "decimals": 6}},
                {"id": "hyperswap-v3", "attributes": {"name": "HyperSwap V3"}},
            ],
        }

        quotes = src._normalize(raw)

        self.assertEqual(len(quotes), 1)
        self.assertEqual(quotes[0].dex, "HyperSwap V3")
        self.assertEqual(quotes[0].ask_price, Decimal("2.50"))
        self.assertEqual(quotes[0].pair.base.chain, "hyperevm")


if __name__ == "__main__":
    unittest.main()
