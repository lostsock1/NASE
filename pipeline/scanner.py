import logging
import time
from decimal import Decimal

from models.types import Opportunity
from pipeline.matcher import MatchedGroup
from util.config import Config

logger = logging.getLogger("nase")

DEFAULT_BRIDGE_COST = 10.00


class Scanner:
    def __init__(self, config: Config):
        self.config = config
        self._gas_estimates = config.chain_gas_estimates
        self._bridge_costs = config.cross_chain_bridge_costs

    def scan(self, groups: list[MatchedGroup]) -> list[Opportunity]:
        opportunities: list[Opportunity] = []

        for group in groups:
            opp = self._scan_group(group)
            if opp:
                opportunities.append(opp)

        logger.info("Scanned: %d opportunities found", len(opportunities))
        return opportunities

    def _scan_group(self, group: MatchedGroup) -> Opportunity | None:
        if not group.quotes:
            return None

        buy = min(group.quotes, key=lambda q: q.ask_price)
        sell = max(group.quotes, key=lambda q: q.bid_price)
        if buy is None or sell is None:
            return None
        if buy.dex == sell.dex and buy.pair.chain == sell.pair.chain:
            return None
        if buy.ask_price <= 0 or sell.bid_price <= 0:
            return None

        spread_pct = float(
            ((sell.bid_price - buy.ask_price) / buy.ask_price) * Decimal("100")
        )
        if spread_pct <= 0:
            return None

        buy_chain = buy.pair.chain
        sell_chain = sell.pair.chain

        cost = self._estimate_cost(buy_chain, sell_chain)
        net = 0.0
        if self.config.capital.amount_usd > 0:
            net = (spread_pct / 100.0) * self.config.capital.amount_usd - cost

        sources = sorted(set(q.source_api for q in group.quotes))
        return Opportunity(
            pair=buy.pair,
            buy_at_dex=buy.dex,
            sell_at_dex=sell.dex,
            buy_price=buy.ask_price,
            sell_price=sell.bid_price,
            spread_pct=round(spread_pct, 4),
            net_profit_usd=round(net, 2),
            buy_chain=buy_chain,
            sell_chain=sell_chain,
            sell_pair_address=sell.pair.pair_address,
            source_apis=sources,
            detected_at=time.time(),
        )

    def _estimate_cost(self, buy_chain: str, sell_chain: str) -> float:
        if buy_chain == sell_chain:
            return self._gas_estimates.get(buy_chain, 5.0)
        key = f"{buy_chain}_to_{sell_chain}"
        key_rev = f"{sell_chain}_to_{buy_chain}"
        return self._bridge_costs.get(key) or self._bridge_costs.get(key_rev) or DEFAULT_BRIDGE_COST
