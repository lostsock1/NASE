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

globalThis.fetch = async (input) => {
  const proxy = new URL(String(input), "http://space-agent.local");
  const target = new URL(proxy.searchParams.get("url"));
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
      related_quotes: [{ executable: true }, { executable: true }],
      analysis: { actionability: "strong_candidate", executable_related_quotes: 2, caveats: [] },
    });
  }
  if (target.pathname === "/api/explain/weak-1") {
    return jsonResponse({
      opportunity: weakOpportunity,
      related_quotes: [],
      analysis: { actionability: "candidate", executable_related_quotes: 0, caveats: ["confidence below 60"] },
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

const intent = await nase.tradeIntentFor("good-1", policy);
assert.equal(intent.status, "intent_requires_executor");
assert.equal(intent.contains_private_key, false);
assert.equal(intent.requires_executor, true);

console.log("helper.test.mjs passed");
