import logging

from models.types import PriceQuote

logger = logging.getLogger("nase")


class MatchedGroup:
    def __init__(self, base_address: str, quote_address: str):
        self.base_address = base_address
        self.quote_address = quote_address
        self.quotes: list[PriceQuote] = []

    @property
    def is_actionable(self) -> bool:
        dexs = {(q.dex, q.pair.chain) for q in self.quotes}
        return len(dexs) >= 2

    @property
    def chains(self) -> set[str]:
        return {q.pair.chain for q in self.quotes}


class Matcher:
    def match(self, quotes: list[PriceQuote]) -> list[MatchedGroup]:
        groups: dict[tuple[str, str], MatchedGroup] = {}

        for q in quotes:
            key = (q.pair.base.address.lower(), q.pair.quote.address.lower())
            if key not in groups:
                groups[key] = MatchedGroup(
                    base_address=q.pair.base.address,
                    quote_address=q.pair.quote.address,
                )
            groups[key].quotes.append(q)

        actionable = [g for g in groups.values() if g.is_actionable]
        logger.info("Matched %d groups, %d actionable (>=2 sources)", len(groups), len(actionable))
        return actionable
