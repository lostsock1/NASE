import assert from "node:assert/strict";

import {
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

const poolOnlyPaper = simulatePaperTrade(
  { ...strongPayload, analysis: { ...strongPayload.analysis, executable_legs: { complete: false } } },
  { alerts: [] },
  policy,
);
assert.equal(poolOnlyPaper.status, "paper_reject");
assert.ok(poolOnlyPaper.reasons.includes("paper mode requires executable buy and sell legs"));

const intent = createTradeIntentDraft(strongPayload, { evaluation, paper }, policy);
assert.equal(intent.status, "intent_requires_executor");
assert.equal(intent.requires_executor, true);
assert.equal(intent.contains_private_key, false);
assert.equal(intent.signing_allowed_here, false);

const weakPaper = simulatePaperTrade(strongPayload, { alerts: [], evaluation }, { ...policy, minNetEdgeUsd: 999 });
assert.equal(weakPaper.status, "paper_reject");

console.log("policy.test.mjs passed");
