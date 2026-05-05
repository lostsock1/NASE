import logging
import time
from statistics import median
from decimal import Decimal

from models.types import Opportunity
from pipeline.matcher import MatchedGroup
from util.config import Config

logger = logging.getLogger("nase")

DEFAULT_BRIDGE_COST = 10.00
MAX_MEDIAN_DEVIATION_PCT = 5.0


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
        quotes = self._without_price_outliers(group.quotes)
        if len(quotes) < 2:
            return None

        buy = min(quotes, key=lambda q: q.ask_price)
        sell = max(quotes, key=lambda q: q.bid_price)
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

        sources = sorted(set(q.source_api for q in quotes))
        max_liquidity = max((q.liquidity_usd for q in quotes), default=0.0)
        confidence = self._confidence_score(quotes)
        notes = tuple(sorted({note for q in quotes for note in q.validation_notes}))
        return Opportunity(
            pair=buy.pair,
            buy_at_dex=buy.dex[:20],
            sell_at_dex=sell.dex[:20],
            buy_price=buy.ask_price,
            sell_price=sell.bid_price,
            spread_pct=round(spread_pct, 4),
            net_profit_usd=round(net, 2),
            buy_chain=buy_chain,
            sell_chain=sell_chain,
            sell_pair_address=sell.pair.pair_address,
            liquidity_usd=max_liquidity,
            confidence_score=confidence,
            validation_notes=notes,
            source_apis=sources,
            detected_at=time.time(),
        )

    @staticmethod
    def _confidence_score(quotes: list) -> int:
        if not quotes:
            return 0
        unique_sources = len({q.source_api for q in quotes})
        executable_count = sum(1 for q in quotes if getattr(q, "executable", False))
        max_liquidity = max((q.liquidity_usd for q in quotes), default=0.0)
        prices = [float(q.mid_price) for q in quotes if q.mid_price > 0]
        med = median(prices) if prices else 0
        deviation = 0.0
        if med > 0 and len(prices) > 1:
            deviation = (max(prices) - min(prices)) / med * 100
        score = 45 + min(20, unique_sources * 5) + min(20, executable_count * 7)
        if max_liquidity >= 1_000_000:
            score += 10
        elif max_liquidity >= 100_000:
            score += 6
        elif max_liquidity >= 10_000:
            score += 3
        score -= int(min(deviation, 10) * 3)
        return max(0, min(99, score))

    @staticmethod
    def _without_price_outliers(quotes: list) -> list:
        if len(quotes) < 3:
            return quotes
        prices = [float(q.mid_price) for q in quotes if q.mid_price > 0]
        if len(prices) < 3:
            return quotes
        med = median(prices)
        if med <= 0:
            return quotes
        filtered = [q for q in quotes if abs(float(q.mid_price) - med) / med * 100 <= MAX_MEDIAN_DEVIATION_PCT]
        return filtered if len(filtered) >= 2 else quotes

    def _estimate_cost(self, buy_chain: str, sell_chain: str) -> float:
        if buy_chain == sell_chain:
            return self._gas_estimates.get(buy_chain, 5.0)
        key = f"{buy_chain}_to_{sell_chain}"
        key_rev = f"{sell_chain}_to_{buy_chain}"
        return self._bridge_costs.get(key) or self._bridge_costs.get(key_rev) or DEFAULT_BRIDGE_COST
