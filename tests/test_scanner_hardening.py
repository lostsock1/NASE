from decimal import Decimal
import unittest

from models.types import Pair, PriceQuote, Token
from pipeline.matcher import MatchedGroup
from pipeline.scanner import Scanner
from util.config import ArbTypes, Capital, Config, Filters


def config():
    return Config(
        refresh_interval_seconds=5,
        arb_types=ArbTypes(),
        filters=Filters(),
        capital=Capital(),
        chain_gas_estimates={"ethereum": 1},
        cross_chain_bridge_costs={},
        sources={},
        chains=["ethereum"],
    )


def quote(price, dex):
    return PriceQuote(
        pair=Pair(
            base=Token("0x1111111111111111111111111111111111111111", "WETH", "ethereum"),
            quote=Token("0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "USDC", "ethereum"),
            pair_address=f"0xpool-{dex}",
        ),
        dex=dex,
        source_api="test",
        ask_price=Decimal(str(price)),
        bid_price=Decimal(str(price)),
    )


class ScannerHardeningTests(unittest.TestCase):
    def test_assigns_confidence_score(self):
        group = MatchedGroup("WETH", "USDC", ("ethereum", "0x1", "0xa"))
        group.quotes = [quote("100", "a"), quote("100.5", "b"), quote("101", "c")]

        opp = Scanner(config())._scan_group(group)

        self.assertIsNotNone(opp)
        self.assertGreaterEqual(opp.confidence_score, 1)

    def test_drops_median_price_outlier_before_scanning(self):
        group = MatchedGroup("WETH", "USDC", ("ethereum", "0x1", "0xa"))
        group.quotes = [quote("100", "a"), quote("101", "b"), quote("200", "bad")]

        opp = Scanner(config())._scan_group(group)

        self.assertIsNotNone(opp)
        self.assertEqual(opp.sell_price, Decimal("101"))


if __name__ == "__main__":
    unittest.main()
