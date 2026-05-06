from decimal import Decimal
import time
import unittest

from models.types import Pair, PriceQuote, Token
from pipeline.normalizer import Normalizer
from util.config import ArbTypes, Capital, Config, Filters


def config(chains=None):
    return Config(
        refresh_interval_seconds=5,
        arb_types=ArbTypes(),
        filters=Filters(),
        capital=Capital(),
        chain_gas_estimates={},
        cross_chain_bridge_costs={},
        sources={},
        chains=chains or ["ethereum"],
    )


def quote(*, chain="ethereum", source="dexscreener", liquidity=20_000, volume=2_000):
    return PriceQuote(
        pair=Pair(
            base=Token("0x1111111111111111111111111111111111111111", "WETH", chain),
            quote=Token("0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "USDC", chain),
            pair_address="0xpool",
        ),
        dex="test",
        source_api=source,
        ask_price=Decimal("1"),
        bid_price=Decimal("1"),
        liquidity_usd=liquidity,
        volume_24h_usd=volume,
        fetched_at=time.time(),
    )


class NormalizerHardeningTests(unittest.TestCase):
    def test_drops_unconfigured_chains(self):
        quotes = Normalizer(config(["ethereum"])).normalize_all({"dexscreener": [quote(chain="pulsechain")]})

        self.assertEqual(quotes, [])

    def test_drops_low_activity_pool_quotes(self):
        quotes = Normalizer(config()).normalize_all({"dexscreener": [quote(liquidity=100, volume=1)]})

        self.assertEqual(quotes, [])

    def test_drops_unexecutable_aggregator_quotes(self):
        quotes = Normalizer(config()).normalize_all({"odos": [quote(source="odos", liquidity=0, volume=0)]})

        self.assertEqual(quotes, [])

    def test_keeps_executable_aggregator_quotes_without_pool_liquidity(self):
        q = quote(source="odos", liquidity=0, volume=0)
        q = type(q)(
            pair=q.pair,
            dex=q.dex,
            source_api=q.source_api,
            ask_price=q.ask_price,
            bid_price=q.bid_price,
            liquidity_usd=q.liquidity_usd,
            volume_24h_usd=q.volume_24h_usd,
            executable=True,
            confidence_score=90,
            fetched_at=q.fetched_at,
        )
        quotes = Normalizer(config()).normalize_all({"odos": [q]})

        self.assertEqual(len(quotes), 1)

    def test_drops_bad_stablecoin_prices(self):
        q = quote(source="dexscreener", liquidity=20_000, volume=2_000)
        q = type(q)(
            pair=Pair(
                base=Token("0x1111111111111111111111111111111111111111", "USDC", "ethereum"),
                quote=Token("0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "USDT", "ethereum"),
                pair_address="0xstable",
            ),
            dex=q.dex,
            source_api=q.source_api,
            ask_price=Decimal("0.72"),
            bid_price=Decimal("0.72"),
            liquidity_usd=q.liquidity_usd,
            volume_24h_usd=q.volume_24h_usd,
            fetched_at=q.fetched_at,
        )
        quotes = Normalizer(config()).normalize_all({"dexscreener": [q]})

        self.assertEqual(quotes, [])


if __name__ == "__main__":
    unittest.main()
