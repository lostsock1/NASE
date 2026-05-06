import assert from "node:assert/strict";

import {
  EXECUTION_STYLES,
  PAPER_EXECUTION_STYLES,
  createTradeIntentDraft,
  evaluateOpportunity,
  normalizePolicy,
  simulatePaperTrade,
} from "../customware/L1/_all/mod/nase/arbitrage/policy.js";

const strongPayload = {
  opportunity: {
    id: "good-1",
    pair: "WETH/USDC",
    base: "WETH",
    quote: "USDC",
    chain: "arbitrum",
    buy_chain: "arbitrum",
    sell_chain: "arbitrum",
    buy_at: "Velora",
    sell_at: "Odos",
    spread_pct: 0.62,
    confidence: 91,
    age_seconds: 12,
    sources: ["velora", "odos", "kyberswap"],
    notes: [],
  },
  related_quotes: [{ executable: true }, { executable: true }],
  analysis: {
    actionability: "strong_candidate",
    executable_related_quotes: 2,
    executable_legs: {
      complete: true,
      buy_quote: { id: "buy", dex: "Velora", price: "2500", executable: true, notional_usd: 1000 },
      sell_quote: { id: "sell", dex: "Odos", price: "2515.5", executable: true, notional_usd: 1000 },
      spread_pct: 0.62,
      max_notional_usd: 1000,
    },
    caveats: [],
  },
};

const policy = normalizePolicy({
  minConfidence: 85,
  minSpreadPct: 0.25,
  paperBudgetUsd: 500,
  maxBudgetPerTradeUsd: 250,
  minNetEdgeUsd: 0.1,
  chainGasUsd: { arbitrum: 0.05 },
});

assert.deepEqual(EXECUTION_STYLES, ["limit_only", "hybrid", "market_exact_in"]);
assert.deepEqual(PAPER_EXECUTION_STYLES, ["market_exact_in", "limit_hypothesis"]);
assert.equal(normalizePolicy({ executionStyle: "market_exact_in" }).executionStyle, "market_exact_in");
assert.equal(normalizePolicy({ liveExecutionStyle: "hybrid" }).liveExecutionStyle, "hybrid");
assert.equal(normalizePolicy({ paperExecutionStyle: "limit_hypothesis" }).paperExecutionStyle, "limit_hypothesis");
assert.equal(normalizePolicy({ executionStyle: "unsupported" }).executionStyle, "limit_only");

const evaluation = evaluateOpportunity(strongPayload, { alerts: [] }, policy);
assert.equal(evaluation.status, "actionable");
assert.equal(evaluation.notify, true);
assert.equal(evaluation.executable_related_quotes, 2);
assert.equal(evaluation.executable_legs.complete, true);

const noExecutable = evaluateOpportunity(
  { ...strongPayload, related_quotes: [], analysis: { ...strongPayload.analysis, executable_related_quotes: 0, executable_legs: { complete: false } } },
  { alerts: [] },
  policy,
);
assert.equal(noExecutable.status, "blocked");
assert.ok(noExecutable.hard_blocks.includes("no executable related quote"));
assert.ok(noExecutable.hard_blocks.includes("missing executable buy/sell leg quote"));

const criticalSource = evaluateOpportunity(
  strongPayload,
  { alerts: [{ type: "source_health", severity: "critical", source: "odos" }] },
  policy,
);
assert.equal(criticalSource.status, "blocked");
assert.ok(criticalSource.hard_blocks.includes("critical source health alert"));

const paper = simulatePaperTrade(strongPayload, { alerts: [], evaluation }, policy);
assert.equal(paper.status, "paper_candidate");
assert.ok(paper.estimated_net_usd > 0);
assert.equal(paper.budget_usd, 250);
assert.equal(paper.executable_buy_price, 2500);
assert.equal(paper.executable_sell_price, 2515.5);
assert.equal(paper.scanner_spread_pct, 0.62);
assert.equal(paper.paper_execution_style, "market_exact_in");
assert.equal(paper.execution_assumption, "market_exact_in_replay");
assert.equal(paper.fill_certainty, "quote_time_executable");
assert.equal(paper.execution_evidence, "executable_quote_depth");
assert.equal(paper.reference_price_kind, "executable_quote_depth");
assert.equal(paper.uses_last_trade_price, false);
assert.match(paper.execution_warning, /latency/);

const limitPaper = simulatePaperTrade(strongPayload, { alerts: [], evaluation }, { ...policy, paperExecutionStyle: "limit_hypothesis" });
assert.equal(limitPaper.status, "paper_candidate");
assert.equal(limitPaper.paper_execution_style, "limit_hypothesis");
assert.equal(limitPaper.execution_assumption, "limit_fill_hypothesis");
assert.equal(limitPaper.fill_certainty, "hypothetical");
assert.match(limitPaper.execution_warning, /cannot know/);

const poolOnlyPaper = simulatePaperTrade(
  { ...strongPayload, analysis: { ...strongPayload.analysis, executable_legs: { complete: false } } },
  { alerts: [] },
  policy,
);
assert.equal(poolOnlyPaper.status, "paper_reject");
assert.ok(poolOnlyPaper.reasons.includes("paper mode requires executable buy and sell legs"));

const lastTradeLikePaper = simulatePaperTrade(
  {
    ...strongPayload,
    related_quotes: [
      { id: "buy-last", dex: "Velora", price: "2500", executable: false },
      { id: "sell-last", dex: "Odos", price: "2515.5", executable: false },
    ],
    analysis: {
      ...strongPayload.analysis,
      executable_related_quotes: 0,
      executable_legs: {
        complete: true,
        buy_quote: { id: "buy-last", dex: "Velora", price: "2500", executable: false },
        sell_quote: { id: "sell-last", dex: "Odos", price: "2515.5", executable: false },
        spread_pct: 0.62,
        max_notional_usd: 0,
      },
    },
  },
  { alerts: [] },
  policy,
);
assert.equal(lastTradeLikePaper.status, "paper_reject");
assert.equal(lastTradeLikePaper.execution_evidence, "non_executable_reference");
assert.ok(lastTradeLikePaper.reasons.includes("paper mode requires executable buy and sell legs"));

const intent = createTradeIntentDraft(strongPayload, { evaluation, paper }, policy);
assert.equal(intent.status, "intent_requires_executor");
assert.equal(intent.requires_executor, true);
assert.equal(intent.contains_private_key, false);
assert.equal(intent.signing_allowed_here, false);
assert.equal(intent.execution_style, "limit_only");
assert.equal(intent.live_execution_style, "limit_only");
assert.equal(intent.paper_execution_style, "market_exact_in");
assert.equal(intent.executor_requirements.market_order_allowed, false);
assert.equal(intent.executor_requirements.limit_order_required, true);
assert.equal(intent.order_plan.legs[0].order_type, "limit");
assert.equal(intent.order_plan.legs[0].max_price, 2500.5);
assert.equal(intent.order_plan.legs[1].min_price, 2514.9969);

const marketIntent = createTradeIntentDraft(strongPayload, { evaluation, paper }, { ...policy, liveExecutionStyle: "market_exact_in", maxLiveSlippageBps: 5 });
assert.equal(marketIntent.execution_style, "market_exact_in");
assert.equal(marketIntent.executor_requirements.market_order_allowed, true);
assert.equal(marketIntent.executor_requirements.limit_order_required, false);
assert.equal(marketIntent.order_plan.legs[0].order_type, "market_exact_in");
assert.equal(marketIntent.order_plan.legs[0].max_slippage_bps, 5);

const hybridIntent = createTradeIntentDraft(strongPayload, { evaluation, paper }, { ...policy, liveExecutionStyle: "hybrid" });
assert.equal(hybridIntent.order_plan.fallback_market_allowed, true);
assert.equal(hybridIntent.order_plan.legs[0].fallback_order_type, "market_exact_in");

const weakPaper = simulatePaperTrade(strongPayload, { alerts: [], evaluation }, { ...policy, minNetEdgeUsd: 999 });
assert.equal(weakPaper.status, "paper_reject");

console.log("policy.test.mjs passed");
