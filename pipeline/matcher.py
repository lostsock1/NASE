import logging

from models.types import PriceQuote

logger = logging.getLogger("nase")


def _norm_address(address: str) -> str:
    return (address or "").strip().lower()


class MatchedGroup:
    def __init__(self, base_symbol: str, quote_symbol: str, key: tuple[str, str, str]):
        self.base_symbol = base_symbol
        self.quote_symbol = quote_symbol
        self.key = key
        self.quotes: list[PriceQuote] = []

    @property
    def is_actionable(self) -> bool:
        markets = {(q.dex, q.source_api, q.pair.pair_address.lower()) for q in self.quotes}
        return len(markets) >= 2

    @property
    def chains(self) -> set[str]:
        return {q.pair.chain for q in self.quotes}


class Matcher:
    def match(self, quotes: list[PriceQuote]) -> list[MatchedGroup]:
        groups: dict[tuple[str, str, str], MatchedGroup] = {}
        skipped = 0

        for q in quotes:
            base_addr = _norm_address(q.pair.base.address)
            quote_addr = _norm_address(q.pair.quote.address)
            if not q.pair.chain or not base_addr or not quote_addr:
                skipped += 1
                continue

            key = (q.pair.chain, base_addr, quote_addr)
            if key not in groups:
                groups[key] = MatchedGroup(
                    base_symbol=q.pair.base.symbol,
                    quote_symbol=q.pair.quote.symbol,
                    key=key,
                )
            groups[key].quotes.append(q)

        actionable = [g for g in groups.values() if g.is_actionable]
        logger.info(
            "Matched %d contract groups, %d actionable, %d skipped",
            len(groups), len(actionable), skipped,
        )
        return actionable
