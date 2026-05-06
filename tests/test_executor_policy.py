from datetime import datetime, timezone
import unittest

from executor.policy import ExecutorConfig, validate_intent


def intent(**overrides):
    payload = {
        "id": "intent-1",
        "opportunity_id": "opp-1",
        "status": "intent_requires_executor",
        "requires_executor": True,
        "contains_private_key": False,
        "signing_allowed_here": False,
        "budget_usd": 100,
        "live_execution_style": "market_exact_in",
        "quote_ttl_seconds": 10,
        "human_confirmation_required": False,
        "executor_requirements": {
            "require_fresh_quote": True,
            "require_transaction_simulation": True,
        },
        "order_plan": {
            "executable_legs_complete": True,
            "legs": [
                {"side": "buy", "max_price": 101},
                {"side": "sell", "min_price": 103},
            ],
        },
    }
    payload.update(overrides)
    return payload


def fresh(**overrides):
    payload = {
        "opportunity": {"age_seconds": 2},
        "analysis": {
            "executable_legs": {
                "complete": True,
                "buy_quote": {"id": "buy", "price": "100", "executable": True, "notional_usd": 500},
                "sell_quote": {"id": "sell", "price": "104", "executable": True, "notional_usd": 500},
                "max_notional_usd": 500,
            }
        },
    }
    payload.update(overrides)
    return payload


class ExecutorPolicyTests(unittest.TestCase):
    def test_accepts_dry_run_when_intent_is_fresh_and_bounded(self):
        decision = validate_intent(intent(), fresh_explain=fresh(), config=ExecutorConfig(), now=datetime(2026, 5, 6, tzinfo=timezone.utc))

        self.assertEqual(decision["status"], "accepted_dry_run")
        self.assertFalse(decision["submitted"])
        self.assertFalse(decision["signed"])
        self.assertEqual(decision["blocks"], [])

    def test_rejects_last_trade_like_fresh_payload(self):
        payload = fresh()
        payload["analysis"]["executable_legs"]["buy_quote"]["executable"] = False

        decision = validate_intent(intent(), fresh_explain=payload, config=ExecutorConfig())

        self.assertEqual(decision["status"], "rejected")
        self.assertIn("fresh explain lacks executable buy/sell legs", decision["blocks"])

    def test_rejects_stale_quote_ttl(self):
        decision = validate_intent(intent(), fresh_explain=fresh(opportunity={"age_seconds": 11}), config=ExecutorConfig())

        self.assertEqual(decision["status"], "rejected")
        self.assertTrue(any("exceeds ttl" in block for block in decision["blocks"]))

    def test_rejects_price_bound_violation(self):
        payload = fresh()
        payload["analysis"]["executable_legs"]["sell_quote"]["price"] = "99"

        decision = validate_intent(intent(), fresh_explain=payload, config=ExecutorConfig())

        self.assertEqual(decision["status"], "rejected")
        self.assertIn("fresh sell price is below min sell price", decision["blocks"])

    def test_rejects_missing_human_confirmation(self):
        decision = validate_intent(intent(human_confirmation_required=True), fresh_explain=fresh(), config=ExecutorConfig())

        self.assertEqual(decision["status"], "rejected")
        self.assertIn("human confirmation required", decision["blocks"])


if __name__ == "__main__":
    unittest.main()
