from decimal import Decimal
import unittest

from sources.lifi import LifiSource
from sources.kyberswap import KyberSwapSource
from sources.odos import OdosSource
from sources.oneinch import OneInchSource
from sources.openocean import OpenOceanSource
from sources.velora import VeloraSource
from sources.zerox import ZeroXSource
from util.config import SourceConfig

CFG = SourceConfig(True, "https://example.test", 1, 1, 15)
BASE = {"address": "0xbase", "symbol": "WETH", "decimals": "18"}
QUOTE = {"address": "0xquote", "symbol": "USDC", "decimals": "6"}
OUT_2500_USDC = "2500000000"


class QuoteAggregatorNormalizeTests(unittest.TestCase):
    def test_openocean_uses_raw_amounts_when_present(self):
        src = OpenOceanSource(CFG, ["ethereum"])
        quote = src._normalize({"data": {"inAmount": "1000000000000000000", "outAmount": OUT_2500_USDC}}, "ethereum", BASE, QUOTE)

        self.assertIsNotNone(quote)
        self.assertEqual(quote.ask_price, Decimal("2500"))
        self.assertEqual(quote.source_api, "openocean")

    def test_openocean_volume_fallback_treats_values_as_human_units(self):
        src = OpenOceanSource(CFG, ["ethereum"])
        quote = src._normalize({"data": {"inToken": {"volume": "1"}, "outToken": {"volume": "2500"}}}, "ethereum", BASE, QUOTE)

        self.assertIsNotNone(quote)
        self.assertEqual(quote.ask_price, Decimal("2500"))

    def test_lifi_normalizes_estimate_to_amount(self):
        src = LifiSource(CFG, ["ethereum"])
        quote = src._normalize({"estimate": {"toAmount": OUT_2500_USDC}, "tool": "1inch"}, "ethereum", BASE, QUOTE)

        self.assertIsNotNone(quote)
        self.assertEqual(quote.ask_price, Decimal("2500"))
        self.assertEqual(quote.dex, "LI.FI:1inch")

    def test_zerox_normalizes_buy_amount(self):
        src = ZeroXSource(CFG, ["ethereum"], api_key="key")
        quote = src._normalize({"buyAmount": OUT_2500_USDC}, "ethereum", BASE, QUOTE)

        self.assertIsNotNone(quote)
        self.assertEqual(quote.ask_price, Decimal("2500"))

    def test_oneinch_normalizes_dst_amount(self):
        src = OneInchSource(CFG, ["ethereum"], api_key="key")
        quote = src._normalize({"dstAmount": OUT_2500_USDC}, "ethereum", BASE, QUOTE)

        self.assertIsNotNone(quote)
        self.assertEqual(quote.ask_price, Decimal("2500"))

    def test_velora_normalizes_price_route(self):
        src = VeloraSource(CFG, ["ethereum"])
        quote = src._normalize({"priceRoute": {"destAmount": OUT_2500_USDC, "contractMethod": "swapExactAmountIn"}}, "ethereum", BASE, QUOTE)

        self.assertIsNotNone(quote)
        self.assertEqual(quote.ask_price, Decimal("2500"))
        self.assertEqual(quote.dex, "Velora:swapExactAmountIn")

    def test_velora_normalizes_custom_input_amount(self):
        src = VeloraSource(CFG, ["ethereum"])
        quote = src._normalize(
            {"priceRoute": {"destAmount": "5000000000", "contractMethod": "swapExactAmountIn"}},
            "ethereum",
            BASE,
            QUOTE,
            "2000000000000000000",
        )

        self.assertIsNotNone(quote)
        self.assertEqual(quote.ask_price, Decimal("2500"))

    def test_odos_normalizes_first_output_amount(self):
        src = OdosSource(CFG, ["ethereum"])
        quote = src._normalize({"outAmounts": [OUT_2500_USDC]}, "ethereum", BASE, QUOTE)

        self.assertIsNotNone(quote)
        self.assertEqual(quote.ask_price, Decimal("2500"))

    def test_kyberswap_normalizes_route_summary(self):
        src = KyberSwapSource(CFG, ["ethereum"])
        quote = src._normalize({"data": {"routeSummary": {"amountOut": OUT_2500_USDC}}}, "ethereum", BASE, QUOTE)

        self.assertIsNotNone(quote)
        self.assertEqual(quote.ask_price, Decimal("2500"))


if __name__ == "__main__":
    unittest.main()
