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

const noExecutable = evaluateOpportunity(
  { ...strongPayload, related_quotes: [], analysis: { ...strongPayload.analysis, executable_related_quotes: 0 } },
  { alerts: [] },
  policy,
);
assert.equal(noExecutable.status, "blocked");
assert.ok(noExecutable.hard_blocks.includes("no executable related quote"));

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

const intent = createTradeIntentDraft(strongPayload, { evaluation, paper }, policy);
assert.equal(intent.status, "intent_requires_executor");
assert.equal(intent.requires_executor, true);
assert.equal(intent.contains_private_key, false);
assert.equal(intent.signing_allowed_here, false);

const weakPaper = simulatePaperTrade(strongPayload, { alerts: [], evaluation }, { ...policy, minNetEdgeUsd: 999 });
assert.equal(weakPaper.status, "paper_reject");

console.log("policy.test.mjs passed");
