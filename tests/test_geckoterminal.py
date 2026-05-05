import unittest

from sources.geckoterminal import GeckoTerminalSource
from util.config import SourceConfig


class GeckoTerminalSourceTests(unittest.TestCase):
    def test_normalize_pool_uses_base_token_usd_price_and_reserve(self):
        source = GeckoTerminalSource(SourceConfig(True, "https://api.geckoterminal.com", 1, 1, 30), ["ethereum"])
        raw = {
            "data": [
                {
                    "id": "eth_0xpool",
                    "attributes": {
                        "address": "0xpool",
                        "base_token_price_usd": "2379.50",
                        "reserve_in_usd": "123456.7",
                        "volume_usd": {"h24": "98765.4"},
                    },
                    "relationships": {
                        "base_token": {"data": {"id": "eth_0xbase"}},
                        "quote_token": {"data": {"id": "eth_0xquote"}},
                        "dex": {"data": {"id": "uniswap_v3"}},
                    },
                }
            ],
            "included": [
                {"id": "eth_0xbase", "type": "token", "attributes": {"address": "0xbase", "symbol": "WETH", "decimals": 18}},
                {"id": "eth_0xquote", "type": "token", "attributes": {"address": "0xquote", "symbol": "USDC", "decimals": 6}},
                {"id": "uniswap_v3", "type": "dex", "attributes": {"name": "Uniswap V3"}},
            ],
        }

        quotes = source._normalize(raw, "ethereum")

        self.assertEqual(len(quotes), 1)
        self.assertEqual(str(quotes[0].ask_price), "2379.50")
        self.assertEqual(quotes[0].liquidity_usd, 123456.7)
        self.assertEqual(quotes[0].volume_24h_usd, 98765.4)
        self.assertEqual(quotes[0].dex, "Uniswap V3")
        self.assertEqual(quotes[0].pair.base.address, "0xbase")
        self.assertEqual(quotes[0].pair.quote.symbol, "USDC")


if __name__ == "__main__":
    unittest.main()
