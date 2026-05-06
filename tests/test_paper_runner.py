import unittest

from executor.paper_runner import (
    PaperRunPolicy,
    evaluate_opportunity,
    normalize_executable_legs,
    simulate_paper_trade,
)


def explain_payload(*, executable=True, age_seconds=2, buy_price="100", sell_price="104"):
    return {
        "opportunity": {
            "id": "opp-1",
            "pair": "WETH/USDC",
            "chain": "arbitrum",
            "buy_chain": "arbitrum",
            "sell_chain": "arbitrum",
            "buy_at": "KyberSwap",
            "sell_at": "Velora",
            "spread_pct": 4,
            "confidence": 92,
            "age_seconds": age_seconds,
            "sources": ["kyberswap", "velora"],
        },
        "analysis": {
            "executable_legs": {
                "complete": True,
                "buy_quote": {"id": "buy", "price": buy_price, "executable": executable, "notional_usd": 500},
                "sell_quote": {"id": "sell", "price": sell_price, "executable": executable, "notional_usd": 500},
                "max_notional_usd": 500,
            }
        },
    }


class PaperRunnerTests(unittest.TestCase):
    def test_accepts_profitable_executable_market_replay(self):
        policy = PaperRunPolicy(min_net_edge_usd=0, paper_budget_usd=100, max_budget_per_trade_usd=100, default_gas_usd=0.01)
        payload = explain_payload()

        evaluation = evaluate_opportunity(payload, [], policy)
        paper = simulate_paper_trade(payload, evaluation, policy)

        self.assertEqual(evaluation["status"], "actionable")
        self.assertEqual(paper["status"], "paper_candidate")
        self.assertEqual(paper["execution_evidence"], "executable_quote_depth")
        self.assertFalse(paper["uses_last_trade_price"])

    def test_rejects_last_trade_like_non_executable_legs(self):
        policy = PaperRunPolicy(min_confidence=0, min_spread_pct=0)
        payload = explain_payload(executable=False)

        evaluation = evaluate_opportunity(payload, [], policy)
        paper = simulate_paper_trade(payload, evaluation, policy)

        self.assertEqual(evaluation["status"], "blocked")
        self.assertEqual(paper["status"], "paper_reject")
        self.assertEqual(paper["execution_evidence"], "non_executable_reference")
        self.assertIn("paper mode requires executable buy and sell legs", paper["reasons"])

    def test_rejects_negative_net_edge(self):
        policy = PaperRunPolicy(min_net_edge_usd=0, paper_budget_usd=100, max_budget_per_trade_usd=100, default_gas_usd=10)
        payload = explain_payload(buy_price="100", sell_price="100.1")

        evaluation = evaluate_opportunity(payload, [], policy)
        paper = simulate_paper_trade(payload, evaluation, policy)

        self.assertEqual(paper["status"], "paper_reject")
        self.assertTrue(any(reason.startswith("net edge") for reason in paper["reasons"]))

    def test_normalizes_max_notional_from_legs_when_declared_zero(self):
        legs = normalize_executable_legs({
            "complete": True,
            "buy_quote": {"id": "buy", "price": "100", "executable": True, "notional_usd": 250},
            "sell_quote": {"id": "sell", "price": "101", "executable": True, "notional_usd": 150},
            "max_notional_usd": 0,
        })

        self.assertTrue(legs["complete"])
        self.assertEqual(legs["max_notional_usd"], 150)


if __name__ == "__main__":
    unittest.main()
