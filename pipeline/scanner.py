import logging
import time
from decimal import Decimal

from models.types import Opportunity
from pipeline.matcher import MatchedGroup
from util.config import Config

logger = logging.getLogger("nase")


class Scanner:
    def __init__(self, config: Config):
        self.config = config
        self._gas_estimates = config.chain_gas_estimates
        self._bridge_costs = config.cross_chain_bridge_costs

    def scan(self, groups: list[MatchedGroup], enabled_arb_types: list[str]) -> list[Opportunity]:
        opportunities: list[Opportunity] = []

        if "simple" in enabled_arb_types:
            for group in groups:
                opp = self._scan_simple(group)
                if opp:
                    opportunities.append(opp)

        if "triangular" in enabled_arb_types:
            tri = self._scan_triangular(groups)
            opportunities.extend(tri)

        if "cross_chain" in enabled_arb_types:
            cross = self._scan_cross_chain(groups)
            opportunities.extend(cross)

        logger.info("Scanned: %d opportunities found", len(opportunities))
        return opportunities

    def _scan_simple(self, group: MatchedGroup) -> Opportunity | None:
        if not group.quotes:
            return None
        buy = min(group.quotes, key=lambda q: q.ask_price)
        sell = max(group.quotes, key=lambda q: q.bid_price)
        if buy is None or sell is None:
            return None
        if buy.dex == sell.dex:
            return None
        if buy.ask_price <= 0 or sell.bid_price <= 0:
            return None

        spread_pct = float(
            ((sell.bid_price - buy.ask_price) / buy.ask_price) * Decimal("100")
        )
        if spread_pct <= 0:
            return None

        gas = self._gas_estimates.get(group.chain, 5.0)
        net = 0.0
        if self.config.capital.amount_usd > 0:
            net = (spread_pct / 100.0) * self.config.capital.amount_usd - gas

        sources = sorted(set(q.source_api for q in group.quotes))
        return Opportunity(
            pair=buy.pair,
            buy_at_dex=buy.dex,
            sell_at_dex=sell.dex,
            buy_price=buy.ask_price,
            sell_price=sell.bid_price,
            spread_pct=round(spread_pct, 4),
            net_profit_usd=round(net, 2),
            source_apis=sources,
            detected_at=time.time(),
        )

    def _scan_triangular(self, groups: list[MatchedGroup]) -> list[Opportunity]:
        return []

    def _scan_cross_chain(self, groups: list[MatchedGroup]) -> list[Opportunity]:
        return []
