import unittest

from sources.dexscreener import DexScreenerSource
from util.config import SourceConfig


class DexScreenerSourceTests(unittest.TestCase):
    def test_normalize_filters_wrong_chain_and_wrong_contract(self):
        src = DexScreenerSource(SourceConfig(True, "https://api.dexscreener.io", 1, 1, 30))
        raw = {
            "pairs": [
                {
                    "chainId": "solana",
                    "pairAddress": "sol-pair",
                    "baseToken": {"address": "So11111111111111111111111111111111111111112", "symbol": "WETH"},
                    "quoteToken": {"address": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "symbol": "USDC"},
                    "priceUsd": "1960",
                    "liquidity": {"usd": 2000000},
                    "volume": {"h24": 200000},
                    "dexId": "raydium",
                },
                {
                    "chainId": "ethereum",
                    "pairAddress": "wrong-contract",
                    "baseToken": {"address": "0x2222222222222222222222222222222222222222", "symbol": "WETH"},
                    "quoteToken": {"address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", "symbol": "USDC"},
                    "priceUsd": "2380",
                    "liquidity": {"usd": 2000000},
                    "volume": {"h24": 200000},
                    "dexId": "uniswap",
                },
                {
                    "chainId": "ethereum",
                    "pairAddress": "right-contract",
                    "baseToken": {"address": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "symbol": "WETH"},
                    "quoteToken": {"address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", "symbol": "USDC"},
                    "priceUsd": "2381",
                    "liquidity": {"usd": 2000000},
                    "volume": {"h24": 200000},
                    "dexId": "uniswap",
                },
            ]
        }

        quotes = src._normalize(raw, "ethereum", "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2")

        self.assertEqual(len(quotes), 1)
        self.assertEqual(quotes[0].pair.pair_address, "right-contract")


if __name__ == "__main__":
    unittest.main()
