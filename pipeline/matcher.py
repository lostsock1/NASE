import logging

from models.types import PriceQuote

logger = logging.getLogger("nase")


class MatchedGroup:
    def __init__(self, chain: str, base_address: str, quote_address: str):
        self.chain = chain
        self.base_address = base_address
        self.quote_address = quote_address
        self.quotes: list[PriceQuote] = []

    @property
    def is_actionable(self) -> bool:
        dexs = {q.dex for q in self.quotes}
        return len(dexs) >= 2


class Matcher:
    def match(self, quotes: list[PriceQuote], enabled_arb_types: list[str]) -> list[MatchedGroup]:
        groups: dict[tuple[str, str, str], MatchedGroup] = {}

        for q in quotes:
            key = (q.pair.chain, q.pair.base.address.lower(), q.pair.quote.address.lower())
            if key not in groups:
                groups[key] = MatchedGroup(
                    chain=q.pair.chain,
                    base_address=q.pair.base.address,
                    quote_address=q.pair.quote.address,
                )
            groups[key].quotes.append(q)

        actionable = [g for g in groups.values() if g.is_actionable]
        logger.info("Matched %d groups, %d actionable (>=2 DEXes)", len(groups), len(actionable))
        return actionable
