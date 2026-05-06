import assert from "node:assert/strict";

import {
  intentToLedger,
  paperToLedger,
  recordExecutionResult,
  summarizeLedger,
} from "../customware/L1/_all/mod/nase/arbitrage/ledger.js";

const paperEntry = {
  id: "paper-1",
  opportunity_id: "good-1",
  pair: "WETH/USDC",
  route: "Velora -> Odos",
  status: "paper_candidate",
  budget_usd: 250,
  estimated_net_usd: 1.14,
  spread_pct: 0.55,
  confidence: 92,
  created_at: "2026-05-06T06:40:00Z",
};

const ledgerRecord = paperToLedger(paperEntry);
assert.equal(ledgerRecord.type, "paper_trade");
assert.equal(ledgerRecord.outcome, "expected_win");
assert.equal(ledgerRecord.expected_net_usd, 1.14);

const settled = recordExecutionResult(ledgerRecord, {
  status: "settled",
  realized_net_usd: -0.35,
  detail: "slippage exceeded paper estimate",
  at: "2026-05-06T06:41:00Z",
});
assert.equal(settled.outcome, "realized_loss");
assert.equal(settled.realized_net_usd, -0.35);
assert.equal(settled.events.length, 2);

const intentRecord = intentToLedger({
  id: "intent-1",
  opportunity_id: "good-1",
  pair: "WETH/USDC",
  status: "intent_requires_executor",
  budget_usd: 250,
  created_at: "2026-05-06T06:42:00Z",
  paper: paperEntry,
});
assert.equal(intentRecord.outcome, "awaiting_executor");

const summary = summarizeLedger([settled, intentRecord]);
assert.equal(summary.total, 2);
assert.equal(summary.paper_trades, 1);
assert.equal(summary.intents, 1);
assert.equal(summary.losses, 1);
assert.equal(summary.awaiting_executor, 1);
assert.equal(summary.realized_net_usd, -0.35);

console.log("ledger.test.mjs passed");
