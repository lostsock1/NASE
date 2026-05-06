import assert from "node:assert/strict";

const goodOpportunity = {
  id: "good-1",
  pair: "WETH/USDC",
  base: "WETH",
  quote: "USDC",
  chain: "arbitrum",
  buy_chain: "arbitrum",
  sell_chain: "arbitrum",
  buy_at: "Velora",
  sell_at: "Odos",
  spread_pct: 0.55,
  confidence: 92,
  age_seconds: 15,
  sources: ["velora", "odos"],
  notes: [],
};

const weakOpportunity = {
  ...goodOpportunity,
  id: "weak-1",
  pair: "QUQ/USDT",
  base: "QUQ",
  quote: "USDT",
  spread_pct: 4.2,
  confidence: 42,
  sources: ["dexpaprika"],
};

function jsonResponse(payload) {
  return {
    ok: true,
    status: 200,
    async json() {
      return payload;
    },
  };
}

globalThis.fetch = async (input, options = {}) => {
  const proxy = new URL(String(input), "http://space-agent.local");
  const target = new URL(proxy.searchParams.get("url"));
  if (target.pathname === "/health") {
    return jsonResponse({ ok: true, service: "nase-executor", live_trading_enabled: false });
  }
  if (target.pathname === "/api/intents/validate" || target.pathname === "/api/intents/submit") {
    const body = JSON.parse(options.body || "{}");
    return jsonResponse({
      id: "decision-1",
      intent_id: body.intent?.id,
      opportunity_id: body.intent?.opportunity_id,
      status: "accepted_dry_run",
      submitted: false,
      signed: false,
      broadcast: false,
      blocks: [],
      warnings: ["live trading disabled; executor will only dry-run and audit"],
      checks: [{ name: "fresh executable legs", ok: true }],
    });
  }
  if (target.pathname === "/api/opportunities") {
    return jsonResponse({ cycle: 7, updated_at: "2026-05-06T06:30:00Z", opportunities: [goodOpportunity, weakOpportunity] });
  }
  if (target.pathname === "/api/alerts") {
    return jsonResponse({ cycle: 7, alerts: [{ type: "quote_depth", severity: "warning", title: "low exec" }] });
  }
  if (target.pathname === "/api/sources") {
    return jsonResponse({ cycle: 7, sources: [{ name: "velora", healthy: true }, { name: "odos", healthy: true }] });
  }
  if (target.pathname === "/api/explain/good-1") {
    return jsonResponse({
      opportunity: goodOpportunity,
      related_quotes: [
        { id: "buy", dex: "Velora", price: "2500", executable: true, notional_usd: 1000 },
        { id: "sell", dex: "Odos", price: "2513.75", executable: true, notional_usd: 1000 },
      ],
      analysis: {
        actionability: "strong_candidate",
        executable_related_quotes: 2,
        executable_legs: {
          complete: true,
          buy_quote: { id: "buy", dex: "Velora", price: "2500", executable: true, notional_usd: 1000 },
          sell_quote: { id: "sell", dex: "Odos", price: "2513.75", executable: true, notional_usd: 1000 },
          spread_pct: 0.55,
          max_notional_usd: 1000,
        },
        caveats: [],
      },
    });
  }
  if (target.pathname === "/api/explain/weak-1") {
    return jsonResponse({
      opportunity: weakOpportunity,
      related_quotes: [],
      analysis: { actionability: "candidate", executable_related_quotes: 0, executable_legs: { complete: false }, caveats: ["confidence below 60"] },
    });
  }
  throw new Error(`unexpected fetch ${target.pathname}`);
};

const nase = await import("../customware/L1/_all/mod/nase/arbitrage/ext/skills/nase-arbitrage/nase.js");

const policy = {
  minConfidence: 85,
  minSpreadPct: 0.25,
  paperBudgetUsd: 500,
  maxBudgetPerTradeUsd: 250,
  minNetEdgeUsd: 0.1,
  chainGasUsd: { arbitrum: 0.05 },
};

const scout = await nase.scoutOnce(policy);
assert.equal(scout.cycle, 7);
assert.equal(scout.actionable_count, 1);
assert.equal(scout.blocked_count, 1);
assert.equal(scout.signals[0].id, "good-1");

const paper = await nase.paperTradeTop(policy);
assert.equal(paper.entries.length, 1);
assert.equal(paper.entries[0].status, "paper_candidate");
assert.equal(paper.entries[0].paper_execution_style, "market_exact_in");
assert.equal(paper.entries[0].fill_certainty, "quote_time_executable");
assert.equal(paper.entries[0].execution_evidence, "executable_quote_depth");
assert.equal(paper.entries[0].uses_last_trade_price, false);

const intent = await nase.tradeIntentFor("good-1", policy);
assert.equal(intent.status, "intent_requires_executor");
assert.equal(intent.contains_private_key, false);
assert.equal(intent.requires_executor, true);
assert.equal(intent.execution_style, "limit_only");
assert.equal(intent.live_execution_style, "limit_only");
assert.equal(intent.paper_execution_style, "market_exact_in");
assert.equal(intent.executor_requirements.require_fresh_quote, true);
assert.equal(intent.order_plan.market_order_allowed, false);

const marketIntent = await nase.tradeIntentFor("good-1", { ...policy, liveExecutionStyle: "market_exact_in", maxLiveSlippageBps: 4 });
assert.equal(marketIntent.execution_style, "market_exact_in");
assert.equal(marketIntent.order_plan.market_order_allowed, true);
assert.equal(marketIntent.order_plan.legs[0].order_type, "market_exact_in");
assert.equal(marketIntent.order_plan.legs[0].max_slippage_bps, 4);

const executorHealth = await nase.executorHealth();
assert.equal(executorHealth.service, "nase-executor");

const executorValidation = await nase.validateIntentWithExecutor(intent);
assert.equal(executorValidation.status, "accepted_dry_run");
assert.equal(executorValidation.intent_id, intent.id);

const executorSubmission = await nase.submitIntentToExecutor(intent);
assert.equal(executorSubmission.status, "accepted_dry_run");
assert.equal(executorSubmission.submitted, false);

console.log("helper.test.mjs passed");
