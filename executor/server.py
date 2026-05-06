from __future__ import annotations

import json
import os
from typing import Any

from aiohttp import ClientSession, web

from executor.ledger import AuditLedger
from executor.paper_runner import PaperRunManager
from executor.policy import ExecutorConfig, validate_intent


def _json_dumps(data: Any) -> str:
    return json.dumps(data, separators=(",", ":"), default=str)


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _config() -> ExecutorConfig:
    styles = {
        item.strip()
        for item in os.getenv("NASE_EXECUTOR_ALLOWED_STYLES", "limit_only,hybrid,market_exact_in").split(",")
        if item.strip()
    }
    return ExecutorConfig(
        live_trading_enabled=_bool_env("NASE_EXECUTOR_LIVE_TRADING_ENABLED", False),
        allowed_execution_styles=styles,
        max_budget_per_trade_usd=_float_env("NASE_EXECUTOR_MAX_TRADE_USD", 250.0),
        max_daily_budget_usd=_float_env("NASE_EXECUTOR_MAX_DAILY_USD", 1000.0),
        require_human_confirmation=_bool_env("NASE_EXECUTOR_REQUIRE_CONFIRMATION", True),
    )


async def health(request: web.Request) -> web.Response:
    return web.json_response({
        "ok": True,
        "service": "nase-executor",
        "live_trading_enabled": request.app["config"].live_trading_enabled,
    }, dumps=_json_dumps)


async def validate(request: web.Request) -> web.Response:
    payload = await request.json()
    result = await _evaluate_payload(request, payload)
    return web.json_response(result, status=200 if result["status"] != "rejected" else 422, dumps=_json_dumps)


async def submit(request: web.Request) -> web.Response:
    payload = await request.json()
    result = await _evaluate_payload(request, payload)
    record = {"kind": "intent_submission", "decision": result, "intent": _intent_from_payload(payload)}
    request.app["ledger"].append(record)
    return web.json_response(result, status=200 if result["status"] != "rejected" else 422, dumps=_json_dumps)


async def ledger(request: web.Request) -> web.Response:
    limit = int(request.query.get("limit", "100"))
    return web.json_response({"records": request.app["ledger"].latest(limit)}, dumps=_json_dumps)


async def start_paper_run(request: web.Request) -> web.Response:
    payload = await request.json()
    run = request.app["paper_runs"].start_run(payload if isinstance(payload, dict) else {})
    return web.json_response(run, dumps=_json_dumps)


async def paper_runs(request: web.Request) -> web.Response:
    return web.json_response({"runs": request.app["paper_runs"].list_runs()}, dumps=_json_dumps)


async def paper_run(request: web.Request) -> web.Response:
    run = request.app["paper_runs"].get_run(request.match_info["id"])
    if run is None:
        return web.json_response({"error": "paper run not found"}, status=404, dumps=_json_dumps)
    return web.json_response(run, dumps=_json_dumps)


async def _evaluate_payload(request: web.Request, payload: dict[str, Any]) -> dict[str, Any]:
    intent = _intent_from_payload(payload)
    fresh_explain = payload.get("fresh_explain") if isinstance(payload, dict) else None
    if fresh_explain is None and intent.get("opportunity_id"):
        fresh_explain = await _fetch_explain(request.app["http"], request.app["nase_api_base"], intent["opportunity_id"])
    return validate_intent(
        intent,
        fresh_explain=fresh_explain,
        config=request.app["config"],
        daily_reserved_usd=request.app["ledger"].reserved_today_usd(),
        human_confirmed=bool(payload.get("human_confirmed")) if isinstance(payload, dict) else False,
    )


def _intent_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload, dict) and isinstance(payload.get("intent"), dict):
        return payload["intent"]
    return payload if isinstance(payload, dict) else {}


async def _fetch_explain(session: ClientSession, base: str, opportunity_id: str) -> dict[str, Any] | None:
    url = f"{base.rstrip('/')}/api/explain/{opportunity_id}"
    try:
        async with session.get(url, timeout=8) as response:
            if response.status != 200:
                return None
            return await response.json()
    except Exception:
        return None


async def make_app() -> web.Application:
    app = web.Application()
    app["config"] = _config()
    app["ledger"] = AuditLedger(os.getenv("NASE_EXECUTOR_LEDGER_PATH", "/tmp/nase-executor-ledger.jsonl"))
    app["nase_api_base"] = os.getenv("NASE_API_BASE", "http://127.0.0.1:8787")
    app.router.add_get("/health", health)
    app.router.add_post("/api/intents/validate", validate)
    app.router.add_post("/api/intents/submit", submit)
    app.router.add_get("/api/ledger", ledger)
    app.router.add_post("/api/paper-runs", start_paper_run)
    app.router.add_get("/api/paper-runs", paper_runs)
    app.router.add_get("/api/paper-runs/{id}", paper_run)

    async def on_startup(app_: web.Application) -> None:
        app_["http"] = ClientSession()
        app_["paper_runs"] = PaperRunManager(
            session=app_["http"],
            nase_api_base=app_["nase_api_base"],
            ledger=app_["ledger"],
        )

    async def on_cleanup(app_: web.Application) -> None:
        await app_["http"].close()

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app


def main() -> None:
    port = int(os.getenv("NASE_EXECUTOR_PORT", "8790"))
    host = os.getenv("NASE_EXECUTOR_HOST", "127.0.0.1")
    web.run_app(make_app(), host=host, port=port)


if __name__ == "__main__":
    main()
