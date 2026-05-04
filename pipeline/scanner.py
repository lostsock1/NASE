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

    def scan(
        self,
        groups: list[MatchedGroup],
        enabled_arb_types: list[str],
        buy_mode: str = "ask",
        sell_mode: str = "bid",
    ) -> list[Opportunity]:
        opportunities: list[Opportunity] = []

        if "simple" in enabled_arb_types:
            for group in groups:
                opp = self._scan_simple(group, buy_mode, sell_mode)
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

    @staticmethod
    def _price(q, mode: str) -> Decimal:
        if mode == "bid":
            return q.bid_price
        if mode == "mid":
            return q.mid_price
        return q.ask_price

    def _scan_simple(
        self, group: MatchedGroup, buy_mode: str, sell_mode: str
    ) -> Opportunity | None:
        if not group.quotes:
            return None
        buy = min(group.quotes, key=lambda q: self._price(q, buy_mode))
        sell = max(group.quotes, key=lambda q: self._price(q, sell_mode))
        if buy is None or sell is None:
            return None
        if buy.dex == sell.dex:
            return None

        buy_p = self._price(buy, buy_mode)
        sell_p = self._price(sell, sell_mode)
        if buy_p <= 0 or sell_p <= 0:
            return None

        spread_pct = float(((sell_p - buy_p) / buy_p) * Decimal("100"))
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
            buy_price=buy_p,
            sell_price=sell_p,
            spread_pct=round(spread_pct, 4),
            net_profit_usd=round(net, 2),
            source_apis=sources,
            detected_at=time.time(),
        )

    def _scan_triangular(self, groups: list[MatchedGroup]) -> list[Opportunity]:
        return []

    def _scan_cross_chain(self, groups: list[MatchedGroup]) -> list[Opportunity]:
        return []
