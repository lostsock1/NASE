import logging

from models.types import Opportunity
from util.config import Config

logger = logging.getLogger("nase")


class ResultFilter:
    def __init__(self, config: Config):
        self.config = config

    def apply(self, opportunities: list[Opportunity]) -> list[Opportunity]:
        if not opportunities:
            return []

        if self.config.capital.amount_usd > 0:
            opps = self._recalculate_for_capital(opportunities)
        else:
            opps = list(opportunities)

        opps = self._filter_by_profit(opps)
        opps = self._deduplicate(opps)
        opps.sort(
            key=lambda o: o.spread_pct if self.config.capital.amount_usd == 0 else o.net_profit_usd,
            reverse=True,
        )
        opps = opps[: self.config.filters.max_opportunities]

        logger.info("Filter: %d opportunities after filtering", len(opps))
        return opps

    def _recalculate_for_capital(self, opportunities: list[Opportunity]) -> list[Opportunity]:
        capital = self.config.capital.amount_usd
        result = []
        for o in opportunities:
            gas = self.config.chain_gas_estimates.get(o.pair.chain, 5.0)
            net = (o.spread_pct / 100.0) * capital - gas
            result.append(
                Opportunity(
                    pair=o.pair,
                    buy_at_dex=o.buy_at_dex,
                    sell_at_dex=o.sell_at_dex,
                    buy_price=o.buy_price,
                    sell_price=o.sell_price,
                    spread_pct=o.spread_pct,
                    net_profit_usd=round(net, 2),
                    buy_chain=o.buy_chain,
                    sell_chain=o.sell_chain,
                    sell_pair_address=o.sell_pair_address,
                    source_apis=o.source_apis,
                    detected_at=o.detected_at,
                )
            )
        return result

    def _filter_by_profit(self, opportunities: list[Opportunity]) -> list[Opportunity]:
        threshold = self.config.filters.min_profit_usd
        if self.config.capital.amount_usd > 0:
            return [o for o in opportunities if o.net_profit_usd >= threshold]
        return opportunities

    def _deduplicate(self, opportunities: list[Opportunity]) -> list[Opportunity]:
        seen: dict[tuple, Opportunity] = {}
        for o in opportunities:
            key = (o.pair.pair_address.lower(), o.buy_at_dex, o.sell_at_dex)
            if key in seen:
                existing = seen[key]
                combined = list(set(existing.source_apis + o.source_apis))
                if o.spread_pct < existing.spread_pct:
                    obj = o
                else:
                    obj = existing
                seen[key] = Opportunity(
                    pair=obj.pair,
                    buy_at_dex=obj.buy_at_dex,
                    sell_at_dex=obj.sell_at_dex,
                    buy_price=obj.buy_price,
                    sell_price=obj.sell_price,
                    spread_pct=obj.spread_pct,
                    net_profit_usd=obj.net_profit_usd,
                    buy_chain=obj.buy_chain,
                    sell_chain=obj.sell_chain,
                    sell_pair_address=obj.sell_pair_address,
                    source_apis=combined,
                    detected_at=min(o.detected_at, existing.detected_at),
                )
            else:
                seen[key] = o
        return list(seen.values())
