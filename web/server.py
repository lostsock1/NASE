from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from aiohttp import web

from models.types import Opportunity, PriceQuote
from pipeline.collector import Collector
from pipeline.filter import ResultFilter
from pipeline.matcher import Matcher
from pipeline.normalizer import Normalizer
from pipeline.scanner import Scanner
from sources.dexscreener import DexScreenerSource
from sources.dexpaprika import DexPaprikaSource
from sources.geckoterminal import GeckoTerminalSource
from sources.jupiter import JupiterSource
from sources.hyperliquid import HyperliquidSource
from sources.hyperswap import HyperSwapSource
from sources.kyberswap import KyberSwapSource
from sources.lifi import LifiSource
from sources.odos import OdosSource
from sources.oneinch import OneInchSource
from sources.openocean import OpenOceanSource
from sources.trafficdex import TrafficDexSource
from sources.velora import VeloraSource
from sources.zerox import ZeroXSource
from util.config import Config, load_config
from util.logging_config import setup_logging

logger = logging.getLogger("nase.web")
ROOT = Path(__file__).resolve().parents[1]
STATIC_ROOT = Path(__file__).resolve().parent / "static"

SOURCE_SPECS = [
    ("dexscreener", DexScreenerSource, "DEXSCREENER_API_KEY", False),
    ("dexpaprika", DexPaprikaSource, "DEXPAPRIKA_API_KEY", True),
    ("geckoterminal", GeckoTerminalSource, "GECKOTERMINAL_API_KEY", True),
    ("jupiter", JupiterSource, "JUPITER_API_KEY", False),
    ("hyperliquid", HyperliquidSource, "HYPERLIQUID_API_KEY", False),
    ("hyperswap", HyperSwapSource, "HYPERSWAP_API_KEY", False),
    ("openocean", OpenOceanSource, "OPENOCEAN_API_KEY", True),
    ("lifi", LifiSource, "LIFI_API_KEY", True),
    ("zerox", ZeroXSource, "ZEROX_API_KEY", True),
    ("oneinch", OneInchSource, "ONEINCH_API_KEY", True),
    ("velora", VeloraSource, "VELORA_API_KEY", True),
    ("odos", OdosSource, "ODOS_API_KEY", True),
    ("kyberswap", KyberSwapSource, "KYBERSWAP_API_KEY", True),
    ("trafficdex", TrafficDexSource, "GECKOTERMINAL_API_KEY", True),
]


def _decimal_str(value: Decimal) -> str:
    return format(value, "f")


def _fmt_float(value: float) -> float:
    try:
        return round(float(value), 8)
    except (TypeError, ValueError):
        return 0.0


def _stable_id(*parts: Any) -> str:
    raw = "|".join(str(part) for part in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


class WebTracker:
    def __init__(self, config: Config):
        self.config = config
        self.collector = Collector(config)
        self.normalizer = Normalizer(config)
        self.matcher = Matcher()
        self.scanner = Scanner(config)
        self.filter = ResultFilter(config)
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None
        self._started = False
        self._cycle_counter = 0
        self._snapshot: dict[str, Any] = self._empty_snapshot()
        self._quotes: list[PriceQuote] = []
        self._opportunities: list[Opportunity] = []
        self._setup_sources()

    def _setup_sources(self) -> None:
        for name, cls, env_name, needs_chains in SOURCE_SPECS:
            cfg = self.config.sources.get(name)
            if not cfg or not cfg.enabled:
                continue
            kwargs: dict[str, Any] = {"api_key": os.getenv(env_name)}
            if needs_chains:
                kwargs["chains"] = self.config.chains
            self.collector.register(cls(cfg, **kwargs))

    async def start(self) -> None:
        if self._started:
            return
        await self.collector.start_all()
        self._started = True
        self._task = asyncio.create_task(self._loop(), name="nase-web-loop")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._started:
            await self.collector.stop_all()
            self._started = False

    async def _loop(self) -> None:
        await self.refresh(reason="startup")
        while True:
            wait = max(float(self.config.refresh_interval_seconds), 15.0)
            await asyncio.sleep(wait)
            await self.refresh(reason="interval")

    async def refresh(self, reason: str = "manual") -> dict[str, Any]:
        if self._lock.locked():
            snap = dict(self._snapshot)
            snap["busy"] = True
            return snap
        async with self._lock:
            started = datetime.now(timezone.utc)
            cycle_start = asyncio.get_running_loop().time()
            error = None
            try:
                raw = await self.collector.collect()
                quotes = self.normalizer.normalize_all(raw)
                groups = self.matcher.match(quotes)
                opps = self.scanner.scan(groups)
                opps = self.filter.apply(opps)
                self._quotes = quotes
                self._opportunities = opps
                self._cycle_counter += 1
                self._snapshot = self._build_snapshot(raw, quotes, groups, opps, started, cycle_start, reason)
            except Exception as exc:  # keep web app alive even if a provider breaks badly
                logger.exception("web refresh failed")
                error = str(exc)
                self._snapshot = {**self._snapshot, "error": error, "busy": False}
            return self._snapshot

    def _build_snapshot(self, raw, quotes, groups, opps, started, cycle_start, reason) -> dict[str, Any]:
        elapsed = asyncio.get_running_loop().time() - cycle_start
        source_counts = {name: len(items) for name, items in raw.items()}
        source_quote_counts: dict[str, int] = {}
        executable_counts: dict[str, int] = {}
        chain_counts: dict[str, int] = {}
        for q in quotes:
            source_quote_counts[q.source_api] = source_quote_counts.get(q.source_api, 0) + 1
            if q.executable:
                executable_counts[q.source_api] = executable_counts.get(q.source_api, 0) + 1
            chain_counts[q.pair.chain] = chain_counts.get(q.pair.chain, 0) + 1

        scores = [o.confidence_score for o in opps]
        spreads = [o.spread_pct for o in opps]
        return {
            "busy": False,
            "error": None,
            "reason": reason,
            "cycle": self._cycle_counter,
            "updated_at": started.isoformat(),
            "elapsed_seconds": round(elapsed, 2),
            "summary": {
                "raw_quotes": sum(source_counts.values()),
                "normalized_quotes": len(quotes),
                "groups": len(groups),
                "opportunities": len(opps),
                "executable_quotes": sum(executable_counts.values()),
                "median_confidence": self._median(scores),
                "best_spread": max(spreads) if spreads else 0,
            },
            "sources": self._sources_payload(source_counts, source_quote_counts, executable_counts),
            "chains": self._sorted_counts(chain_counts),
            "opportunities": [self._opportunity_payload(o) for o in opps[:100]],
            "top_quotes": [self._quote_payload(q) for q in sorted(quotes, key=lambda q: q.confidence_score, reverse=True)[:80]],
        }

    def _sources_payload(self, raw_counts, quote_counts, executable_counts):
        statuses = self.collector.source_statuses
        payload = []
        for name, info in statuses.items():
            payload.append({
                "name": name,
                "healthy": bool(info.get("healthy")),
                "rate_limited": bool(info.get("rate_limited")),
                "circuit_open": bool(info.get("circuit_open")),
                "wait": round(float(info.get("rate_wait_seconds", 0)), 1),
                "success_rate": float(info.get("success_rate", 100)),
                "consecutive_failures": int(info.get("consecutive_failures") or 0),
                "last_error": info.get("last_error"),
                "raw": raw_counts.get(name, 0),
                "normalized": quote_counts.get(name, 0),
                "executable": executable_counts.get(name, 0),
            })
        return payload

    def _opportunity_payload(self, o: Opportunity) -> dict[str, Any]:
        pair = f"{o.pair.base.symbol}/{o.pair.quote.symbol}"
        return {
            "id": _stable_id(pair, o.pair.chain, o.buy_at_dex, o.sell_at_dex, o.buy_price, o.sell_price, o.spread_pct),
            "pair": pair,
            "base": o.pair.base.symbol,
            "quote": o.pair.quote.symbol,
            "chain": o.pair.chain,
            "buy_chain": o.buy_chain,
            "sell_chain": o.sell_chain,
            "buy_at": o.buy_at_dex,
            "sell_at": o.sell_at_dex,
            "buy_price": _decimal_str(o.buy_price),
            "sell_price": _decimal_str(o.sell_price),
            "spread_pct": o.spread_pct,
            "net_profit_usd": o.net_profit_usd,
            "liquidity_usd": _fmt_float(o.liquidity_usd),
            "confidence": o.confidence_score,
            "notes": list(o.validation_notes),
            "sources": o.source_apis,
            "age_seconds": round(o.age_seconds, 1),
        }

    def _quote_payload(self, q: PriceQuote) -> dict[str, Any]:
        pair = f"{q.pair.base.symbol}/{q.pair.quote.symbol}"
        return {
            "id": _stable_id(pair, q.pair.chain, q.dex, q.source_api, q.mid_price, q.executable),
            "pair": pair,
            "chain": q.pair.chain,
            "dex": q.dex,
            "source": q.source_api,
            "price": _decimal_str(q.mid_price),
            "liquidity_usd": _fmt_float(q.liquidity_usd),
            "volume_24h_usd": _fmt_float(q.volume_24h_usd),
            "confidence": q.confidence_score,
            "executable": q.executable,
            "notional_usd": q.notional_usd,
            "notes": list(q.validation_notes),
        }

    def sources_payload(self) -> dict[str, Any]:
        return {
            "cycle": self._snapshot.get("cycle", 0),
            "updated_at": self._snapshot.get("updated_at"),
            "summary": self._snapshot.get("summary", {}),
            "sources": self._snapshot.get("sources", []),
        }

    def opportunities_payload(self, request: web.Request) -> dict[str, Any]:
        items = list(self._snapshot.get("opportunities", []))
        chain = request.query.get("chain")
        min_confidence = self._query_float(request, "min_confidence", 0)
        min_spread = self._query_float(request, "min_spread", 0)
        limit = int(self._query_float(request, "limit", 100))
        limit = max(1, min(limit, 250))

        if chain:
            items = [item for item in items if item.get("chain") == chain or item.get("buy_chain") == chain or item.get("sell_chain") == chain]
        if min_confidence:
            items = [item for item in items if float(item.get("confidence", 0)) >= min_confidence]
        if min_spread:
            items = [item for item in items if float(item.get("spread_pct", 0)) >= min_spread]

        return {
            "cycle": self._snapshot.get("cycle", 0),
            "updated_at": self._snapshot.get("updated_at"),
            "count": len(items[:limit]),
            "opportunities": items[:limit],
        }

    def alerts_payload(self) -> dict[str, Any]:
        alerts: list[dict[str, Any]] = []
        summary = self._snapshot.get("summary", {})

        for source in self._snapshot.get("sources", []):
            if source.get("circuit_open") or source.get("rate_limited") or not source.get("healthy", True):
                severity = "warning" if source.get("success_rate", 100) >= 80 else "critical"
                alerts.append({
                    "id": _stable_id("source", source.get("name"), source.get("wait"), source.get("healthy")),
                    "type": "source_health",
                    "severity": severity,
                    "title": f"{source.get('name')} is constrained",
                    "detail": f"healthy={source.get('healthy')} rate_limited={source.get('rate_limited')} circuit_open={source.get('circuit_open')} wait={source.get('wait')}s failures={source.get('consecutive_failures', 0)} last_error={source.get('last_error') or 'none'}",
                    "source": source.get("name"),
                })

        executable_quotes = int(summary.get("executable_quotes") or 0)
        if executable_quotes < 10:
            alerts.append({
                "id": _stable_id("executable_quotes", executable_quotes, self._snapshot.get("cycle", 0)),
                "type": "quote_depth",
                "severity": "warning",
                "title": "Executable quote coverage is low",
                "detail": f"Only {executable_quotes} executable quotes are present in the latest snapshot.",
            })

        for item in self._snapshot.get("opportunities", [])[:25]:
            confidence = float(item.get("confidence") or 0)
            spread = float(item.get("spread_pct") or 0)
            if spread >= 2 and confidence < 60:
                alerts.append({
                    "id": _stable_id("low_confidence_spread", item.get("id")),
                    "type": "opportunity_review",
                    "severity": "info",
                    "title": f"Review {item.get('pair')} before acting",
                    "detail": f"Spread is {spread:.3f}% but confidence is only {confidence:.0f}. Treat this as a candidate, not an execution signal.",
                    "opportunity_id": item.get("id"),
                })

        return {
            "cycle": self._snapshot.get("cycle", 0),
            "updated_at": self._snapshot.get("updated_at"),
            "count": len(alerts),
            "alerts": alerts,
        }

    def explain_payload(self, identifier: str) -> dict[str, Any] | None:
        opportunities = list(self._snapshot.get("opportunities", []))
        selected = None
        if identifier.isdigit():
            index = int(identifier)
            if 0 <= index < len(opportunities):
                selected = opportunities[index]
        if selected is None:
            selected = next((item for item in opportunities if item.get("id") == identifier), None)
        if selected is None:
            return None

        related_quotes = [
            self._quote_payload(q)
            for q in self._quotes
            if f"{q.pair.base.symbol}/{q.pair.quote.symbol}" == selected.get("pair")
            and q.pair.chain in {selected.get("chain"), selected.get("buy_chain"), selected.get("sell_chain")}
        ]
        related_quotes = sorted(related_quotes, key=lambda item: item.get("confidence", 0), reverse=True)[:20]

        confidence = float(selected.get("confidence") or 0)
        spread = float(selected.get("spread_pct") or 0)
        executable_count = sum(1 for q in related_quotes if q.get("executable"))
        executable_legs = self._executable_legs(selected, related_quotes)
        caveats = []
        if confidence < 60:
            caveats.append("confidence below 60; verify source agreement and pool depth before acting")
        if not executable_legs["complete"]:
            caveats.append("missing executable buy/sell leg quote for paper trading")
        if not selected.get("liquidity_usd"):
            caveats.append("liquidity is unknown or zero in normalized data")

        return {
            "id": selected.get("id"),
            "cycle": self._snapshot.get("cycle", 0),
            "updated_at": self._snapshot.get("updated_at"),
            "opportunity": selected,
            "related_quotes": related_quotes,
            "analysis": {
                "summary": f"{selected.get('pair')} shows a {spread:.3f}% spread from {selected.get('buy_at')} to {selected.get('sell_at')} on {selected.get('chain')}.",
                "confidence": confidence,
                "sources": selected.get("sources", []),
                "executable_related_quotes": executable_count,
                "executable_legs": executable_legs,
                "caveats": caveats,
                "actionability": "candidate" if caveats else "strong_candidate",
            },
        }

    def _executable_legs(self, selected: dict[str, Any], related_quotes: list[dict[str, Any]]) -> dict[str, Any]:
        executable = [q for q in related_quotes if q.get("executable")]
        buy_target = str(selected.get("buy_at") or "")
        sell_target = str(selected.get("sell_at") or "")
        buy_quote = self._match_executable_quote(executable, buy_target, prefer_low=True)
        sell_quote = self._match_executable_quote(executable, sell_target, prefer_low=False)
        complete = bool(buy_quote and sell_quote and buy_quote.get("id") != sell_quote.get("id"))
        spread_pct = 0.0
        max_notional = 0.0
        if complete:
            buy_price = float(buy_quote.get("price") or 0)
            sell_price = float(sell_quote.get("price") or 0)
            if buy_price > 0 and sell_price > 0:
                spread_pct = ((sell_price - buy_price) / buy_price) * 100
            max_notional = min(float(buy_quote.get("notional_usd") or 0), float(sell_quote.get("notional_usd") or 0))
        return {
            "complete": complete,
            "buy_quote": buy_quote,
            "sell_quote": sell_quote,
            "spread_pct": round(spread_pct, 6),
            "max_notional_usd": max_notional,
            "source": "executable_related_quotes",
        }

    @staticmethod
    def _match_executable_quote(quotes: list[dict[str, Any]], target: str, prefer_low: bool) -> dict[str, Any] | None:
        if not quotes:
            return None
        target_norm = target.lower()
        matched = [
            q for q in quotes
            if target_norm
            and (
                str(q.get("dex") or "").lower().startswith(target_norm)
                or target_norm.startswith(str(q.get("dex") or "").lower())
            )
        ]
        candidates = matched or quotes
        return sorted(candidates, key=lambda q: float(q.get("price") or 0), reverse=not prefer_low)[0]

    @staticmethod
    def _query_float(request: web.Request, name: str, default: float) -> float:
        try:
            return float(request.query.get(name, default))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _sorted_counts(counts: dict[str, int]) -> list[dict[str, Any]]:
        return [{"name": k, "count": v} for k, v in sorted(counts.items(), key=lambda item: item[1], reverse=True)]

    @staticmethod
    def _median(values: list[float | int]) -> float:
        if not values:
            return 0.0
        values = sorted(values)
        mid = len(values) // 2
        if len(values) % 2:
            return float(values[mid])
        return round((values[mid - 1] + values[mid]) / 2, 2)

    def _empty_snapshot(self):
        return {
            "busy": True,
            "error": None,
            "cycle": 0,
            "updated_at": None,
            "elapsed_seconds": 0,
            "summary": {"raw_quotes": 0, "normalized_quotes": 0, "groups": 0, "opportunities": 0, "executable_quotes": 0, "median_confidence": 0, "best_spread": 0},
            "sources": [],
            "chains": [],
            "opportunities": [],
            "top_quotes": [],
        }


async def index(_request: web.Request) -> web.FileResponse:
    return web.FileResponse(STATIC_ROOT / "index.html")


async def snapshot(request: web.Request) -> web.Response:
    tracker: WebTracker = request.app["tracker"]
    return web.json_response(tracker._snapshot, dumps=_json_dumps)


async def refresh(request: web.Request) -> web.Response:
    tracker: WebTracker = request.app["tracker"]
    data = await tracker.refresh(reason="manual")
    return web.json_response(data, dumps=_json_dumps)


async def sources(request: web.Request) -> web.Response:
    tracker: WebTracker = request.app["tracker"]
    return web.json_response(tracker.sources_payload(), dumps=_json_dumps)


async def opportunities(request: web.Request) -> web.Response:
    tracker: WebTracker = request.app["tracker"]
    return web.json_response(tracker.opportunities_payload(request), dumps=_json_dumps)


async def alerts(request: web.Request) -> web.Response:
    tracker: WebTracker = request.app["tracker"]
    return web.json_response(tracker.alerts_payload(), dumps=_json_dumps)


async def explain(request: web.Request) -> web.Response:
    tracker: WebTracker = request.app["tracker"]
    data = tracker.explain_payload(request.match_info["id"])
    if data is None:
        return web.json_response({"error": "opportunity not found"}, status=404, dumps=_json_dumps)
    return web.json_response(data, dumps=_json_dumps)


def _json_dumps(data: Any) -> str:
    return json.dumps(data, separators=(",", ":"), default=str)


async def make_app() -> web.Application:
    setup_logging()
    config = load_config(str(ROOT / "config.yaml"), str(ROOT / ".env"))
    tracker = WebTracker(config)
    app = web.Application()
    app["tracker"] = tracker
    app.router.add_get("/", index)
    app.router.add_get("/api/snapshot", snapshot)
    app.router.add_get("/api/sources", sources)
    app.router.add_get("/api/opportunities", opportunities)
    app.router.add_get("/api/alerts", alerts)
    app.router.add_get("/api/explain/{id}", explain)
    app.router.add_post("/api/refresh", refresh)
    app.router.add_static("/static", STATIC_ROOT, append_version=True)

    async def on_startup(_app):
        await tracker.start()

    async def on_cleanup(_app):
        await tracker.stop()

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app


def main() -> None:
    port = int(os.getenv("NASE_WEB_PORT", "8787"))
    host = os.getenv("NASE_WEB_HOST", "127.0.0.1")
    web.run_app(make_app(), host=host, port=port)


if __name__ == "__main__":
    main()
