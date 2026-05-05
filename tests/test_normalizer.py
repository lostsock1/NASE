from decimal import Decimal
import time
import unittest

from models.types import Pair, PriceQuote, Token
from pipeline.normalizer import Normalizer
from util.config import ArbTypes, Capital, Config, Filters


def config(refresh=5):
    return Config(
        refresh_interval_seconds=refresh,
        arb_types=ArbTypes(),
        filters=Filters(),
        capital=Capital(),
        chain_gas_estimates={},
        cross_chain_bridge_costs={},
        sources={},
        chains=["ethereum"],
    )


def quote(age_seconds):
    return PriceQuote(
        pair=Pair(
            base=Token("0x1111111111111111111111111111111111111111", "WETH", "ethereum"),
            quote=Token("0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "USDC", "ethereum"),
            pair_address="0xpool",
        ),
        dex="test",
        source_api="test",
        ask_price=Decimal("1"),
        bid_price=Decimal("1"),
        fetched_at=time.time() - age_seconds,
    )


class NormalizerTests(unittest.TestCase):
    def test_keeps_quotes_from_slow_network_cycle(self):
        quotes = Normalizer(config(refresh=5)).normalize_all({"test": [quote(45)]})

        self.assertEqual(len(quotes), 1)

    def test_drops_stale_quotes(self):
        quotes = Normalizer(config(refresh=5)).normalize_all({"test": [quote(180)]})

        self.assertEqual(quotes, [])


if __name__ == "__main__":
    unittest.main()
