from decimal import Decimal
import unittest

from models.types import Pair, PriceQuote, Token
from pipeline.matcher import Matcher


def quote(base_addr: str, quote_addr: str, base_symbol: str = "ABC", quote_symbol: str = "USDC", dex: str = "dex") -> PriceQuote:
    return PriceQuote(
        pair=Pair(
            base=Token(address=base_addr, symbol=base_symbol, chain="ethereum"),
            quote=Token(address=quote_addr, symbol=quote_symbol, chain="ethereum"),
            pair_address=f"{base_addr}-{quote_addr}-{dex}",
        ),
        dex=dex,
        source_api="test",
        ask_price=Decimal("1"),
        bid_price=Decimal("1"),
    )


class MatcherTests(unittest.TestCase):
    def test_same_symbols_different_contracts_do_not_match(self):
        groups = Matcher().match([
            quote("0x1111111111111111111111111111111111111111", "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", dex="one"),
            quote("0x2222222222222222222222222222222222222222", "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", dex="two"),
        ])

        self.assertEqual(groups, [])

    def test_same_contract_market_matches_across_dexes(self):
        groups = Matcher().match([
            quote("0x1111111111111111111111111111111111111111", "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", dex="one"),
            quote("0x1111111111111111111111111111111111111111", "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", dex="two"),
        ])

        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0].quotes), 2)

    def test_reversed_pair_orientation_does_not_match(self):
        groups = Matcher().match([
            quote("0x1111111111111111111111111111111111111111", "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "WETH", "USDC", "one"),
            quote("0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "0x1111111111111111111111111111111111111111", "USDC", "WETH", "two"),
        ])

        self.assertEqual(groups, [])


if __name__ == "__main__":
    unittest.main()
