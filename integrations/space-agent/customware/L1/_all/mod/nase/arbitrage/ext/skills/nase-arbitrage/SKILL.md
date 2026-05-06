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
```

Rules:

- Treat NASE as the quote engine; Space Agent is the workspace and analysis layer.
- Prefer `nase.snapshot()` over hand-built fetch URLs.
- When judging quote reliability, cite `confidence`, `executable`, `notes`, source mix, and source health.
- Mention provider backoff explicitly when OpenOcean, LI.FI, or trafficdex are rate-limited.
- Do not claim an opportunity is executable unless its quote has `executable: true` or `exec_depth` in notes.
- For dashboard navigation, use `nase.dashboardUrl`.
