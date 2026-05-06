---
name: NASE Arbitrage
description: Inspect live NASE arbitrage tracker data, executable quote depth, source health, and quote sanity.
metadata:
  when: true
  loaded:
    tags: [nase-arbitrage]
  placement: system
---

Use this skill for questions about the NASE arbitrage tracker running on this VM.

Load helpers:

```js
const nase = await import("/mod/nase/arbitrage/ext/skills/nase-arbitrage/nase.js");
```

Core calls:

```js
const snapshot = await nase.snapshot();
const top = await nase.topOpportunities(10);
const sources = await nase.sourceHealth();
const executable = await nase.executableQuotes();
const sanity = await nase.executableWethUsdcSanity();
const scout = await nase.scoutOnce({ minConfidence: 85, minSpreadPct: 0.25 });
const paper = await nase.paperTradeTop({ paperBudgetUsd: 500, maxBudgetPerTradeUsd: 250 });
const intent = await nase.tradeIntentFor("<opportunity-id>");
const checked = await nase.validateIntentWithExecutor(intent);
const submitted = await nase.submitIntentToExecutor(intent);
const run = await nase.startPaperRun({ duration_seconds: 600, interval_seconds: 30 });
const runs = await nase.paperRuns();
```

Rules:

- Treat NASE as the quote engine; Space Agent is the workspace and analysis layer.
- Prefer `nase.snapshot()` over hand-built fetch URLs.
- When judging quote reliability, cite `confidence`, `executable`, `notes`, source mix, and source health.
- Mention provider backoff explicitly when OpenOcean, LI.FI, or trafficdex are rate-limited.
- Do not claim an opportunity is executable unless its quote has `executable: true` or `exec_depth` in notes.
- Treat ticker, pool midpoint, or last-trade prices as discovery signals only, not paper-trade execution evidence.
- Treat `scoutOnce()` actionable signals as notification candidates, not guaranteed profit.
- Treat `paperTradeTop()` entries as simulated journal records, not fills; market paper records are quote-time executable replays, while limit paper records are fill hypotheses.
- Treat `tradeIntentFor()` as a draft that requires a separate executor; it never signs and never contains private keys.
- Treat `validateIntentWithExecutor()` and `submitIntentToExecutor()` as server-side guard/audit calls; by default they dry-run and do not sign or broadcast.
- Treat `startPaperRun()` as a server-side paper-trading run; it writes audit records and does not sign or broadcast.
- For dashboard navigation, use `nase.dashboardUrl`.
