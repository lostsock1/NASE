from decimal import Decimal
import unittest

from sources.jupiter import JupiterSource, USDC_MINT
from util.config import SourceConfig


class JupiterSourceTests(unittest.TestCase):
    def test_normalize_quote_converts_one_base_token_to_usdc_price(self):
        src = JupiterSource(SourceConfig(True, "https://lite-api.jup.ag", 1, 1, 15))
        token = {"address": "So11111111111111111111111111111111111111112", "symbol": "WSOL", "decimals": "9"}
        quote = src._normalize_quote({"inAmount": "1000000000", "outAmount": "150000000"}, token)

        self.assertIsNotNone(quote)
        self.assertEqual(quote.pair.base.symbol, "WSOL")
        self.assertEqual(quote.pair.quote.address, USDC_MINT)
        self.assertEqual(quote.ask_price, Decimal("150"))
        self.assertEqual(quote.source_api, "jupiter")


if __name__ == "__main__":
    unittest.main()
