# Space Agent Integration

This directory contains the optional Space Agent integration pack for NASE.

It is intentionally stored under `integrations/space-agent/` instead of inside `web/`, `pipeline/`, or `sources/`.

## Boundary

NASE remains the quote engine:

- source adapters
- normalization
- matching
- confidence scoring
- opportunity scanning
- JSON API
- operator web console

Space Agent remains a consumer:

- workspace panel
- agent skill
- API helper
- scout workflows
- paper-trading workflows
- future trade-intent creation

Do not put Space Agent runtime code into NASE core. Do not vendor the Space Agent repository into NASE.

## Contents

```text
customware/
  L1/_all/mod/nase/arbitrage/
    view.html
    store.js
    arbitrage.css
    ext/panels/nase-arbitrage.yaml
    ext/skills/nase-arbitrage/SKILL.md
    ext/skills/nase-arbitrage/nase.js
```

This is a Space Agent `CUSTOMWARE_PATH` tree. It is meant to be mounted by Space Agent at runtime.

## Required NASE API

The integration expects NASE to be running at:

```text
http://127.0.0.1:8787
```

It uses:

- `GET /api/snapshot`
- `GET /api/sources`
- `GET /api/opportunities`
- `GET /api/alerts`
- `GET /api/explain/:id`
- `POST /api/refresh`

The browser helper calls NASE through Space Agent's `/api/proxy`, so the browser does not need direct access to localhost NASE endpoints when Space Agent is exposed through a tunnel.

## Running

Start NASE:

```bash
cd /path/to/NASE
.venv/bin/python -m pip install -e .
NASE_WEB_HOST=127.0.0.1 NASE_WEB_PORT=8787 .venv/bin/nase-web
```

Start Space Agent separately:

```bash
git clone https://github.com/agent0ai/space-agent.git ../space-agent-nase
cd ../space-agent-nase
npm install
CUSTOMWARE_PATH=../NASE/integrations/space-agent/customware \
SINGLE_USER_APP=true \
LOGIN_ALLOWED=false \
HOST=127.0.0.1 \
PORT=8788 \
node space serve
```

Open:

```text
http://127.0.0.1:8788/enter?next=%2F%23%2Fnase%2Farbitrage
```

## Docker

From the NASE repo root:

```bash
docker compose up --build
```

Compose starts NASE and Space Agent together. It mounts this integration pack into Space Agent through `CUSTOMWARE_PATH` and overlays:

```text
docker/space-agent-nase-config.js
```

That file points the browser helper at `http://nase-web:8787` through Space Agent's server-side proxy. Local non-Docker runs use the default:

```text
customware/L1/_all/mod/nase/arbitrage/config.js
```

## Agent Skill

Inside Space Agent, load:

```js
const nase = await import("/mod/nase/arbitrage/ext/skills/nase-arbitrage/nase.js");
```

Useful calls:

```js
await nase.sources();
await nase.opportunities({ limit: 10, min_confidence: 80 });
await nase.alerts();
await nase.explain(0);
await nase.scoutOnce({ minConfidence: 85, minSpreadPct: 0.25 });
await nase.paperTradeTop({ paperBudgetUsd: 500 });
await nase.tradeIntentFor("<opportunity-id>");
await nase.executableWethUsdcSanity();
```

## Scout Mode

Scout Mode watches `/api/alerts`, `/api/opportunities`, and `/api/explain/:id`, then notifies the operator only when a candidate clears strict thresholds.

Suggested defaults:

- confidence >= 85
- executable related quote exists
- source health has no critical blocker for the route
- spread remains above a configured threshold
- token and chain are allowlisted
- quote age is acceptable

Implemented modules:

- `policy.js`: policy normalization, opportunity evaluation, ranking, paper simulation, and trade-intent drafting
- `nase.js`: async Space Agent helper that calls NASE and applies the policy module
- `store.js`: browser orchestration and local persistence

## Paper Armed Mode

Paper Armed Mode simulates only when the explained opportunity has executable buy and sell leg quotes. It rejects pool-only candidates.

It simulates:

- budget allocation
- gross edge from executable leg prices
- DEX fees
- slippage
- gas
- latency haircut
- confidence haircut
- expected net PnL

It writes both a paper journal and a trade ledger before any live mode is considered.

## Trade Ledger

The ledger lives in:

```text
customware/L1/_all/mod/nase/arbitrage/ledger.js
```

It tracks:

- paper simulations
- trade-intent drafts
- expected net PnL
- realized net PnL when an execution result is recorded
- win/loss/skipped/blocked/awaiting-executor outcomes
- timestamped lifecycle events

The workspace can mark ledger rows as win, loss, or skipped. A future executor can feed real fills into the same ledger shape.

## Live Armed Mode Boundary

Live Armed Mode must not live in browser customware. The current implementation only creates guarded trade-intent drafts.

Space Agent may create a trade intent. A separate executor must own:

- private keys
- signing
- budget vault
- chain allowlists
- token allowlists
- kill switch
- transaction simulation
- on-chain submission

NASE should not sign transactions. Space Agent should not hold private keys in browser storage.
