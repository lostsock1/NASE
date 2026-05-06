from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from aiohttp import ClientSession

from executor.ledger import AuditLedger


@dataclass(frozen=True)
class PaperRunPolicy:
    min_confidence: float = 70.0
    min_spread_pct: float = 0.05
    min_net_edge_usd: float = 0.0
    max_age_seconds: float = 180.0
    paper_budget_usd: float = 250.0
    max_budget_per_trade_usd: float = 100.0
    slippage_bps: float = 12.0
    dex_fee_bps: float = 6.0
    latency_haircut_bps: float = 4.0
    confidence_haircut_pct: float = 0.25
    default_gas_usd: float = 1.0
    chain_gas_usd: dict[str, float] = field(default_factory=lambda: {
        "ethereum": 8.0,
        "arbitrum": 0.5,
        "base": 0.3,
        "optimism": 0.3,
        "polygon": 0.1,
        "bsc": 0.25,
        "avalanche": 0.4,
        "solana": 0.01,
        "zksync": 0.2,
        "linea": 0.25,
    })


class PaperRunManager:
    def __init__(self, *, session: ClientSession, nase_api_base: str, ledger: AuditLedger):
        self.session = session
        self.nase_api_base = nase_api_base.rstrip("/")
        self.ledger = ledger
        self.runs: dict[str, dict[str, Any]] = {}
        self.tasks: dict[str, asyncio.Task] = {}

    def start_run(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        duration_seconds = clamp_number(payload.get("duration_seconds"), 600, 30, 86_400)
        interval_seconds = clamp_number(payload.get("interval_seconds"), 30, 5, 3_600)
        max_opportunities = int(clamp_number(payload.get("max_opportunities"), 12, 1, 50))
        policy = policy_from_payload(payload.get("policy") if isinstance(payload.get("policy"), dict) else {})
        now = datetime.now(timezone.utc)
        run_id = stable_id("paper-run", now.isoformat(), duration_seconds, interval_seconds)
        run = {
            "id": run_id,
            "status": "running",
            "duration_seconds": duration_seconds,
            "interval_seconds": interval_seconds,
            "max_opportunities": max_opportunities,
            "started_at": now.isoformat(),
            "finished_at": None,
            "cycles": 0,
            "candidates": 0,
            "accepted": 0,
            "rejected": 0,
            "errors": [],
            "latest_entries": [],
            "policy": policy_to_payload(policy),
        }
        self.runs[run_id] = run
        self.tasks[run_id] = asyncio.create_task(self._run(run, policy), name=f"nase-paper-run-{run_id}")
        self.ledger.append({"kind": "paper_run_started", "run": public_run(run)})
        return public_run(run)

    def list_runs(self) -> list[dict[str, Any]]:
        return [public_run(run) for run in sorted(self.runs.values(), key=lambda item: item["started_at"], reverse=True)]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        run = self.runs.get(run_id)
        return public_run(run) if run else None

    async def _run(self, run: dict[str, Any], policy: PaperRunPolicy) -> None:
        started = asyncio.get_running_loop().time()
        deadline = started + float(run["duration_seconds"])
        try:
            while asyncio.get_running_loop().time() < deadline:
                await self._cycle(run, policy)
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    break
                await asyncio.sleep(min(float(run["interval_seconds"]), remaining))
            run["status"] = "completed"
        except asyncio.CancelledError:
            run["status"] = "cancelled"
            raise
        except Exception as exc:
            run["status"] = "failed"
            run["errors"].append(str(exc))
        finally:
            run["finished_at"] = datetime.now(timezone.utc).isoformat()
            self.ledger.append({"kind": "paper_run_finished", "run": public_run(run)})

    async def _cycle(self, run: dict[str, Any], policy: PaperRunPolicy) -> None:
        run["cycles"] += 1
        cycle = run["cycles"]
        try:
            opportunities, alerts, sources = await asyncio.gather(
                self._get_json(f"/api/opportunities?limit={run['max_opportunities']}&min_confidence=50&min_spread=0"),
                self._get_json("/api/alerts"),
                self._get_json("/api/sources"),
            )
            alert_items = alerts.get("alerts", [])
            source_items = sources.get("sources", [])
            for opportunity in opportunities.get("opportunities", [])[: int(run["max_opportunities"])]:
                explain = await self._get_json(f"/api/explain/{opportunity.get('id')}")
                evaluation = evaluate_opportunity(explain, alert_items, policy)
                if evaluation["status"] == "blocked":
                    continue
                paper = simulate_paper_trade(explain, evaluation, policy)
                run["candidates"] += 1
                if paper["status"] == "paper_candidate":
                    run["accepted"] += 1
                else:
                    run["rejected"] += 1
                entry = {
                    "run_id": run["id"],
                    "cycle": cycle,
                    "at": datetime.now(timezone.utc).isoformat(),
                    "evaluation_status": evaluation["status"],
                    "paper": paper,
                    "source_count": len(source_items),
                }
                run["latest_entries"] = ([entry] + run["latest_entries"])[:25]
                self.ledger.append({"kind": "paper_run_entry", **entry})
        except Exception as exc:
            run["errors"].append(str(exc))
            self.ledger.append({"kind": "paper_run_error", "run_id": run["id"], "cycle": cycle, "error": str(exc)})

    async def _get_json(self, path: str) -> dict[str, Any]:
        async with self.session.get(f"{self.nase_api_base}{path}", timeout=10) as response:
            if response.status != 200:
                raise RuntimeError(f"NASE {path} HTTP {response.status}")
            return await response.json()


def evaluate_opportunity(explain_payload: dict[str, Any], alerts: list[dict[str, Any]], policy: PaperRunPolicy) -> dict[str, Any]:
    opportunity = explain_payload.get("opportunity") if isinstance(explain_payload.get("opportunity"), dict) else {}
    analysis = explain_payload.get("analysis") if isinstance(explain_payload.get("analysis"), dict) else {}
    confidence = number(opportunity.get("confidence", analysis.get("confidence")), 0.0)
    spread_pct = number(opportunity.get("spread_pct"), 0.0)
    age_seconds = number(opportunity.get("age_seconds"), 0.0)
    sources = {str(item).lower() for item in opportunity.get("sources", [])}
    critical_sources = {
        str(alert.get("source")).lower()
        for alert in alerts
        if alert.get("type") == "source_health" and alert.get("severity") == "critical"
    }
    legs = normalize_executable_legs(analysis.get("executable_legs"))
    hard_blocks: list[str] = []
    if not opportunity.get("id"):
        hard_blocks.append("missing opportunity id")
    if confidence < policy.min_confidence:
        hard_blocks.append(f"confidence {confidence:.0f} < {policy.min_confidence:g}")
    if spread_pct < policy.min_spread_pct:
        hard_blocks.append(f"spread {spread_pct:.3f}% < {policy.min_spread_pct:g}%")
    if policy.max_age_seconds > 0 and age_seconds > policy.max_age_seconds:
        hard_blocks.append(f"quote age {age_seconds:.0f}s > {policy.max_age_seconds:g}s")
    if not legs["complete"]:
        hard_blocks.append("missing executable buy/sell leg quote")
    if sources.intersection(critical_sources):
        hard_blocks.append("critical source health alert")
    return {
        "id": opportunity.get("id"),
        "pair": opportunity.get("pair", ""),
        "buy_at": opportunity.get("buy_at"),
        "sell_at": opportunity.get("sell_at"),
        "buy_chain": opportunity.get("buy_chain") or opportunity.get("chain"),
        "sell_chain": opportunity.get("sell_chain") or opportunity.get("chain"),
        "confidence": confidence,
        "spread_pct": spread_pct,
        "status": "blocked" if hard_blocks else "actionable",
        "hard_blocks": hard_blocks,
        "executable_legs": legs,
        "opportunity": opportunity,
    }


def simulate_paper_trade(explain_payload: dict[str, Any], evaluation: dict[str, Any], policy: PaperRunPolicy) -> dict[str, Any]:
    legs = evaluation["executable_legs"]
    budget = min(policy.paper_budget_usd, policy.max_budget_per_trade_usd or policy.paper_budget_usd)
    tradable_budget = min(budget, legs["max_notional_usd"]) if legs["max_notional_usd"] > 0 else budget
    executable_spread_pct = legs["spread_pct"]
    gross_edge_usd = tradable_budget * (executable_spread_pct / 100)
    dex_fee_usd = tradable_budget * ((policy.dex_fee_bps * 2) / 10000)
    slippage_usd = tradable_budget * ((policy.slippage_bps * 2) / 10000)
    gas_usd = gas_for(evaluation.get("buy_chain"), policy) + gas_for(evaluation.get("sell_chain"), policy)
    latency_haircut_usd = gross_edge_usd * (policy.latency_haircut_bps / 10000)
    confidence_haircut_usd = gross_edge_usd * ((100 - evaluation["confidence"]) / 100) * policy.confidence_haircut_pct
    estimated_net_usd = gross_edge_usd - dex_fee_usd - slippage_usd - gas_usd - latency_haircut_usd - confidence_haircut_usd
    reasons = list(evaluation["hard_blocks"])
    if not legs["complete"]:
        reasons.append("paper mode requires executable buy and sell legs")
    if executable_spread_pct <= 0:
        reasons.append("non-positive executable spread")
    if estimated_net_usd < policy.min_net_edge_usd:
        reasons.append(f"net edge {round2(estimated_net_usd)} < {policy.min_net_edge_usd:g}")
    blocked = bool(reasons)
    return {
        "id": stable_id("paper", evaluation["id"], datetime.now(timezone.utc).isoformat()),
        "opportunity_id": evaluation["id"],
        "pair": evaluation["pair"],
        "route": f"{evaluation.get('buy_at') or 'buy'} -> {evaluation.get('sell_at') or 'sell'}",
        "status": "paper_reject" if blocked else "paper_candidate",
        "paper_execution_style": "market_exact_in",
        "execution_evidence": legs["evidence_type"],
        "reference_price_kind": "executable_quote_depth" if legs["complete"] else "non_executable_reference",
        "uses_last_trade_price": False,
        "fill_certainty": "quote_time_executable" if legs["complete"] else "not_executable",
        "budget_usd": round2(tradable_budget),
        "requested_budget_usd": round2(budget),
        "max_notional_usd": round2(legs["max_notional_usd"]),
        "executable_buy_price": legs["buy_price"],
        "executable_sell_price": legs["sell_price"],
        "executable_spread_pct": round6(executable_spread_pct),
        "gross_edge_usd": round2(gross_edge_usd),
        "dex_fee_usd": round2(dex_fee_usd),
        "slippage_usd": round2(slippage_usd),
        "gas_usd": round2(gas_usd),
        "latency_haircut_usd": round2(latency_haircut_usd),
        "confidence_haircut_usd": round2(confidence_haircut_usd),
        "estimated_net_usd": round2(estimated_net_usd),
        "confidence": evaluation["confidence"],
        "spread_pct": executable_spread_pct,
        "scanner_spread_pct": evaluation["spread_pct"],
        "reasons": reasons,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "opportunity": evaluation["opportunity"],
        "executable_legs": legs,
    }


def normalize_executable_legs(raw: Any) -> dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    buy = raw.get("buy_quote") if isinstance(raw.get("buy_quote"), dict) else {}
    sell = raw.get("sell_quote") if isinstance(raw.get("sell_quote"), dict) else {}
    buy_price = number(buy.get("price"), 0.0)
    sell_price = number(sell.get("price"), 0.0)
    buy_notional = number(buy.get("notional_usd"), 0.0)
    sell_notional = number(sell.get("notional_usd"), 0.0)
    declared_max_notional = number(raw.get("max_notional_usd"), 0.0)
    fallback_max_notional = min(buy_notional, sell_notional) if buy_notional > 0 and sell_notional > 0 else 0.0
    max_notional = declared_max_notional or fallback_max_notional
    complete = bool(raw.get("complete") and buy.get("executable") is True and sell.get("executable") is True and buy_price > 0 and sell_price > 0 and max_notional > 0)
    spread_pct = ((sell_price - buy_price) / buy_price * 100) if complete else 0.0
    return {
        "complete": complete,
        "buy_quote": buy,
        "sell_quote": sell,
        "buy_price": buy_price,
        "sell_price": sell_price,
        "spread_pct": round6(spread_pct),
        "max_notional_usd": max_notional,
        "evidence_type": "executable_quote_depth" if complete else "non_executable_reference",
    }


def policy_from_payload(payload: dict[str, Any]) -> PaperRunPolicy:
    return PaperRunPolicy(
        min_confidence=number(payload.get("minConfidence", payload.get("min_confidence")), 70.0),
        min_spread_pct=number(payload.get("minSpreadPct", payload.get("min_spread_pct")), 0.05),
        min_net_edge_usd=number(payload.get("minNetEdgeUsd", payload.get("min_net_edge_usd")), 0.0),
        max_age_seconds=number(payload.get("maxAgeSeconds", payload.get("max_age_seconds")), 180.0),
        paper_budget_usd=number(payload.get("paperBudgetUsd", payload.get("paper_budget_usd")), 250.0),
        max_budget_per_trade_usd=number(payload.get("maxBudgetPerTradeUsd", payload.get("max_budget_per_trade_usd")), 100.0),
        slippage_bps=number(payload.get("slippageBps", payload.get("slippage_bps")), 12.0),
        dex_fee_bps=number(payload.get("dexFeeBps", payload.get("dex_fee_bps")), 6.0),
        latency_haircut_bps=number(payload.get("latencyHaircutBps", payload.get("latency_haircut_bps")), 4.0),
        confidence_haircut_pct=number(payload.get("confidenceHaircutPct", payload.get("confidence_haircut_pct")), 0.25),
    )


def policy_to_payload(policy: PaperRunPolicy) -> dict[str, Any]:
    return {
        "min_confidence": policy.min_confidence,
        "min_spread_pct": policy.min_spread_pct,
        "min_net_edge_usd": policy.min_net_edge_usd,
        "max_age_seconds": policy.max_age_seconds,
        "paper_budget_usd": policy.paper_budget_usd,
        "max_budget_per_trade_usd": policy.max_budget_per_trade_usd,
        "slippage_bps": policy.slippage_bps,
        "dex_fee_bps": policy.dex_fee_bps,
        "latency_haircut_bps": policy.latency_haircut_bps,
        "confidence_haircut_pct": policy.confidence_haircut_pct,
    }


def public_run(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": run["id"],
        "status": run["status"],
        "duration_seconds": run["duration_seconds"],
        "interval_seconds": run["interval_seconds"],
        "max_opportunities": run["max_opportunities"],
        "started_at": run["started_at"],
        "finished_at": run["finished_at"],
        "cycles": run["cycles"],
        "candidates": run["candidates"],
        "accepted": run["accepted"],
        "rejected": run["rejected"],
        "errors": run["errors"][-5:],
        "latest_entries": run["latest_entries"][:10],
        "policy": run["policy"],
    }


def gas_for(chain: str | None, policy: PaperRunPolicy) -> float:
    return policy.chain_gas_usd.get(str(chain or "").lower(), policy.default_gas_usd)


def number(value: Any, fallback: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return fallback
    return parsed


def clamp_number(value: Any, fallback: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, number(value, fallback)))


def round2(value: float) -> float:
    return round(float(value or 0), 2)


def round6(value: float) -> float:
    return round(float(value or 0), 6)


def stable_id(*parts: Any) -> str:
    raw = "|".join(str(part) for part in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
