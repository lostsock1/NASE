from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


LIVE_EXECUTION_STYLES = {"limit_only", "hybrid", "market_exact_in"}


@dataclass(frozen=True)
class ExecutorConfig:
    live_trading_enabled: bool = False
    allowed_execution_styles: set[str] = field(default_factory=lambda: set(LIVE_EXECUTION_STYLES))
    max_budget_per_trade_usd: float = 250.0
    max_daily_budget_usd: float = 1000.0
    require_human_confirmation: bool = True


def validate_intent(
    intent: dict[str, Any],
    *,
    fresh_explain: dict[str, Any] | None,
    config: ExecutorConfig | None = None,
    daily_reserved_usd: float = 0.0,
    human_confirmed: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    cfg = config or ExecutorConfig()
    now = now or datetime.now(timezone.utc)
    blocks: list[str] = []
    warnings: list[str] = []
    checks: list[dict[str, Any]] = []

    if not isinstance(intent, dict):
        return _decision("rejected", {}, ["intent must be an object"], [], [], now)

    order_plan = intent.get("order_plan") if isinstance(intent.get("order_plan"), dict) else {}
    executor_requirements = intent.get("executor_requirements") if isinstance(intent.get("executor_requirements"), dict) else {}
    budget_usd = _number(intent.get("budget_usd"), 0.0)
    live_style = str(intent.get("live_execution_style") or intent.get("execution_style") or "")
    quote_ttl_seconds = max(1, int(_number(intent.get("quote_ttl_seconds") or order_plan.get("quote_ttl_seconds"), 10)))

    _check(checks, "intent status", intent.get("status") == "intent_requires_executor", blocks, "intent is not executor-ready")
    _check(checks, "executor boundary", intent.get("requires_executor") is True, blocks, "intent does not require executor")
    _check(checks, "no private key", intent.get("contains_private_key") is False, blocks, "intent contains private key material")
    _check(checks, "signing disabled in agent", intent.get("signing_allowed_here") is False, blocks, "intent allows browser-side signing")
    _check(checks, "execution style allowed", live_style in cfg.allowed_execution_styles, blocks, f"execution style {live_style or '<missing>'} is not allowed")
    _check(checks, "executable leg plan", order_plan.get("executable_legs_complete") is True, blocks, "intent order plan lacks executable legs")
    _check(checks, "fresh quote required", executor_requirements.get("require_fresh_quote") is True, blocks, "intent does not require fresh executor quote")
    _check(checks, "transaction simulation required", executor_requirements.get("require_transaction_simulation") is True, blocks, "intent does not require transaction simulation")
    _check(checks, "trade budget", budget_usd > 0 and budget_usd <= cfg.max_budget_per_trade_usd, blocks, f"budget {budget_usd} exceeds executor max {cfg.max_budget_per_trade_usd}")
    _check(checks, "daily budget", daily_reserved_usd + budget_usd <= cfg.max_daily_budget_usd, blocks, "daily budget would be exceeded")

    if intent.get("human_confirmation_required") and cfg.require_human_confirmation and not human_confirmed:
        blocks.append("human confirmation required")
        checks.append({"name": "human confirmation", "ok": False})
    else:
        checks.append({"name": "human confirmation", "ok": True})

    if cfg.live_trading_enabled:
        warnings.append("live trading is enabled; signer adapter still must enforce vault and chain policy")
    else:
        warnings.append("live trading disabled; executor will only dry-run and audit")

    fresh = _fresh_leg_check(intent, fresh_explain, quote_ttl_seconds)
    checks.extend(fresh["checks"])
    blocks.extend(fresh["blocks"])
    warnings.extend(fresh["warnings"])

    status = "rejected" if blocks else ("accepted_executor_ready" if cfg.live_trading_enabled else "accepted_dry_run")
    return _decision(status, intent, blocks, warnings, checks, now, fresh=fresh.get("fresh"))


def _fresh_leg_check(intent: dict[str, Any], fresh_explain: dict[str, Any] | None, quote_ttl_seconds: int) -> dict[str, Any]:
    blocks: list[str] = []
    warnings: list[str] = []
    checks: list[dict[str, Any]] = []
    if not fresh_explain:
        blocks.append("missing fresh NASE explain payload")
        checks.append({"name": "fresh explain", "ok": False})
        return {"blocks": blocks, "warnings": warnings, "checks": checks, "fresh": None}

    opportunity = fresh_explain.get("opportunity") if isinstance(fresh_explain.get("opportunity"), dict) else {}
    legs = _normalize_fresh_legs(fresh_explain)
    age_seconds = _number(opportunity.get("age_seconds"), 0.0)
    budget_usd = _number(intent.get("budget_usd"), 0.0)
    order_plan = intent.get("order_plan") if isinstance(intent.get("order_plan"), dict) else {}
    planned_legs = order_plan.get("legs") if isinstance(order_plan.get("legs"), list) else []
    buy_plan = next((leg for leg in planned_legs if leg.get("side") == "buy"), {})
    sell_plan = next((leg for leg in planned_legs if leg.get("side") == "sell"), {})

    _check(checks, "fresh explain", bool(fresh_explain.get("analysis")), blocks, "fresh explain payload missing analysis")
    _check(checks, "quote ttl", age_seconds <= quote_ttl_seconds, blocks, f"fresh opportunity age {age_seconds:.1f}s exceeds ttl {quote_ttl_seconds}s")
    _check(checks, "fresh executable legs", legs["complete"], blocks, "fresh explain lacks executable buy/sell legs")
    _check(checks, "fresh notional", legs["max_notional_usd"] >= budget_usd, blocks, "fresh executable notional is below budget")
    _check(checks, "fresh spread", legs["spread_pct"] > 0, blocks, "fresh executable spread is not positive")

    max_buy = _number(buy_plan.get("max_price"), 0.0)
    min_sell = _number(sell_plan.get("min_price"), 0.0)
    if max_buy > 0:
        _check(checks, "buy price bound", legs["buy_price"] <= max_buy, blocks, "fresh buy price exceeds max buy price")
    if min_sell > 0:
        _check(checks, "sell price bound", legs["sell_price"] >= min_sell, blocks, "fresh sell price is below min sell price")

    return {"blocks": blocks, "warnings": warnings, "checks": checks, "fresh": legs}


def _normalize_fresh_legs(payload: dict[str, Any]) -> dict[str, Any]:
    raw = payload.get("analysis", {}).get("executable_legs") if isinstance(payload.get("analysis"), dict) else {}
    raw = raw if isinstance(raw, dict) else {}
    buy = raw.get("buy_quote") if isinstance(raw.get("buy_quote"), dict) else {}
    sell = raw.get("sell_quote") if isinstance(raw.get("sell_quote"), dict) else {}
    buy_price = _number(buy.get("price"), 0.0)
    sell_price = _number(sell.get("price"), 0.0)
    buy_notional = _number(buy.get("notional_usd"), 0.0)
    sell_notional = _number(sell.get("notional_usd"), 0.0)
    declared_max_notional = _number(raw.get("max_notional_usd"), 0.0)
    fallback_max_notional = min(buy_notional, sell_notional) if buy_notional > 0 and sell_notional > 0 else 0.0
    max_notional = declared_max_notional or fallback_max_notional
    complete = bool(raw.get("complete") and buy.get("executable") is True and sell.get("executable") is True and buy_price > 0 and sell_price > 0 and max_notional > 0)
    spread_pct = ((sell_price - buy_price) / buy_price * 100) if complete else 0.0
    return {
        "complete": complete,
        "buy_quote_id": buy.get("id"),
        "sell_quote_id": sell.get("id"),
        "buy_price": buy_price,
        "sell_price": sell_price,
        "spread_pct": round(spread_pct, 6),
        "max_notional_usd": max_notional,
    }


def _decision(status: str, intent: dict[str, Any], blocks: list[str], warnings: list[str], checks: list[dict[str, Any]], now: datetime, *, fresh: dict[str, Any] | None = None) -> dict[str, Any]:
    raw_id = "|".join([str(intent.get("id")), status, now.isoformat()])
    return {
        "id": hashlib.sha1(raw_id.encode("utf-8")).hexdigest()[:16],
        "intent_id": intent.get("id"),
        "opportunity_id": intent.get("opportunity_id"),
        "status": status,
        "submitted": False,
        "signed": False,
        "broadcast": False,
        "blocks": blocks,
        "warnings": warnings,
        "checks": checks,
        "fresh": fresh,
        "created_at": now.isoformat(),
    }


def _check(checks: list[dict[str, Any]], name: str, ok: bool, blocks: list[str], block_message: str) -> None:
    checks.append({"name": name, "ok": bool(ok)})
    if not ok:
        blocks.append(block_message)


def _number(value: Any, fallback: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number
