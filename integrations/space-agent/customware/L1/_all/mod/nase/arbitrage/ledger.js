import { stableId } from "./policy.js";

export function paperToLedger(entry) {
  return {
    id: stableId("ledger", entry.id, entry.created_at),
    type: "paper_trade",
    opportunity_id: entry.opportunity_id,
    pair: entry.pair,
    route: entry.route,
    status: entry.status,
    outcome: entry.estimated_net_usd > 0 ? "expected_win" : "expected_loss",
    budget_usd: entry.budget_usd,
    expected_net_usd: entry.estimated_net_usd,
    realized_net_usd: null,
    spread_pct: entry.spread_pct,
    confidence: entry.confidence,
    created_at: entry.created_at,
    updated_at: entry.created_at,
    events: [
      {
        type: "paper_simulated",
        at: entry.created_at,
        detail: `expected net ${entry.estimated_net_usd}`,
      },
    ],
    source: entry,
  };
}

export function intentToLedger(intent) {
  return {
    id: stableId("ledger", intent.id, intent.created_at),
    type: "trade_intent",
    opportunity_id: intent.opportunity_id,
    pair: intent.pair,
    route: intent.paper?.route || "",
    status: intent.status,
    outcome: intent.status === "blocked" ? "blocked" : "awaiting_executor",
    budget_usd: intent.budget_usd,
    expected_net_usd: intent.paper?.estimated_net_usd ?? null,
    realized_net_usd: null,
    spread_pct: intent.paper?.spread_pct ?? null,
    confidence: intent.paper?.confidence ?? null,
    created_at: intent.created_at,
    updated_at: intent.created_at,
    events: [
      {
        type: "intent_created",
        at: intent.created_at,
        detail: intent.status,
      },
    ],
    source: intent,
  };
}

export function recordExecutionResult(record, execution = {}) {
  const now = execution.at || new Date().toISOString();
  const realized = Number.isFinite(Number(execution.realized_net_usd)) ? Number(execution.realized_net_usd) : record.realized_net_usd;
  let outcome = record.outcome;
  if (realized !== null && realized !== undefined) {
    if (realized > 0) outcome = "realized_win";
    else if (realized < 0) outcome = "realized_loss";
    else outcome = "breakeven";
  }
  if (execution.status === "skipped") outcome = "skipped";
  if (execution.status === "failed") outcome = "failed";
  return {
    ...record,
    status: execution.status || record.status,
    outcome,
    realized_net_usd: realized,
    updated_at: now,
    events: [
      ...(record.events || []),
      {
        type: "execution_update",
        at: now,
        detail: execution.detail || execution.status || outcome,
      },
    ],
  };
}

export function summarizeLedger(records = []) {
  const summary = {
    total: records.length,
    paper_trades: 0,
    intents: 0,
    expected_net_usd: 0,
    realized_net_usd: 0,
    realized_count: 0,
    wins: 0,
    losses: 0,
    blocked: 0,
    awaiting_executor: 0,
  };
  for (const record of records) {
    if (record.type === "paper_trade") summary.paper_trades += 1;
    if (record.type === "trade_intent") summary.intents += 1;
    summary.expected_net_usd += Number(record.expected_net_usd || 0);
    if (record.realized_net_usd !== null && record.realized_net_usd !== undefined) {
      summary.realized_count += 1;
      summary.realized_net_usd += Number(record.realized_net_usd || 0);
    }
    if (record.outcome === "realized_win" || record.outcome === "expected_win") summary.wins += 1;
    if (record.outcome === "realized_loss" || record.outcome === "expected_loss") summary.losses += 1;
    if (record.outcome === "blocked") summary.blocked += 1;
    if (record.outcome === "awaiting_executor") summary.awaiting_executor += 1;
  }
  summary.expected_net_usd = round2(summary.expected_net_usd);
  summary.realized_net_usd = round2(summary.realized_net_usd);
  summary.win_rate = summary.wins + summary.losses > 0 ? round2((summary.wins / (summary.wins + summary.losses)) * 100) : 0;
  return summary;
}

export function normalizeLedger(records = []) {
  return records
    .filter((record) => record && record.id)
    .map((record) => ({
      events: [],
      ...record,
      events: Array.isArray(record.events) ? record.events : [],
    }))
    .slice(0, 100);
}

function round2(value) {
  return Math.round(Number(value || 0) * 100) / 100;
}
