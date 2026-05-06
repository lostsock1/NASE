# NASE

NASE is an arbitrage tracking system for comparing DEX and aggregator quotes across high-traffic chains and liquidity venues. It is built as a quote intelligence engine first: collect quotes, normalize them into one model, match comparable pairs, score confidence, filter weak candidates, and expose the result through a terminal UI, web console, and API.

The project is intentionally split into layers:

- `sources/`: quote and pool data adapters.
- `pipeline/`: collection, normalization, matching, scanning, and filtering.
- `models/`: shared quote, pair, token, and opportunity types.
- `tui/`: terminal interface.
- `web/`: web console and JSON API for dashboards and agent integrations.
- `integrations/`: optional consumers that use NASE data without becoming part of the quote engine.

## Current Capabilities

NASE currently combines broad pool discovery with executable quote checks where possible.

Enabled sources in `config.yaml` include:

- DexScreener
- DexPaprika
- Jupiter
- Hyperliquid
- HyperSwap
- OpenOcean
- LI.FI
- Velora / ParaSwap
- Odos
- KyberSwap
- Traffic DEX discovery through GeckoTerminal-style pool data

Additional source adapters exist for 0x, 1inch, GeckoTerminal, and LiveCoinWatch, but some are disabled or require API keys.

Tracked chains include Ethereum, Arbitrum, Base, Optimism, Polygon, BNB Chain, Avalanche, Solana, Hyperliquid, HyperEVM, Linea, and zkSync.

## Why The Web Console Exists

The web console is not a marketing page. It is an operator surface for checking whether an apparent spread is worth attention.

It shows:

- ranked opportunities
- raw and normalized quote counts
- executable quote coverage
- source health, rate limits, and circuit breakers
- chain coverage
- confidence scores
- quote audit rows
- validation notes such as executable depth checks

The frontend escapes quote, source, DEX, and route strings before rendering. This matters because external market data can contain arbitrary token symbols or venue labels.

## Running Locally

Create and install an environment:

```bash
python -m venv .venv
.venv/bin/python -m pip install -e .
```

Run the terminal UI:

```bash
.venv/bin/nase
```

Run the web console:

```bash
NASE_WEB_HOST=127.0.0.1 NASE_WEB_PORT=8787 .venv/bin/nase-web
```

Open:

```text
http://127.0.0.1:8787
```

## Configuration

The main runtime config is `config.yaml`. Secrets are loaded from `.env`.

Do not commit real API keys. The `.env` file is ignored for new clones, but this repository has historically tracked one `.env` file. Treat any local modifications to `.env` as private machine state and stage code paths explicitly.

Useful knobs:

- `refresh_interval_seconds`: background collection interval.
- `filters.max_opportunities`: maximum opportunities emitted by the filter layer.
- `capital.amount_usd`: capital assumption for profitability math.
- `chain_gas_estimates`: rough per-chain gas estimates.
- `sources.<name>.enabled`: enable or disable a source.
- `sources.<name>.max_rps`: source-level rate limit.
- `sources.<name>.timeout_seconds`: source request timeout.

## Web API

The web app exposes JSON endpoints for dashboards, scripts, and agents.

### `GET /api/snapshot`

Returns the full current tracker snapshot:

- summary metrics
- source health
- chain counts
- top opportunities
- top confidence quotes

### `POST /api/refresh`

Forces a collection cycle and returns the new snapshot. If another cycle is already running, the response marks the snapshot as busy.

### `GET /api/sources`

Returns source health and counts:

- `healthy`
- `rate_limited`
- `circuit_open`
- `wait`
- `success_rate`
- `raw`
- `normalized`
- `executable`

This endpoint is the right input for monitoring provider health and rate-limit behavior.

### `GET /api/opportunities`

Returns ranked opportunities, with optional query filters:

```text
/api/opportunities?limit=25
/api/opportunities?chain=arbitrum
/api/opportunities?min_confidence=80
/api/opportunities?min_spread=0.25
```

Every opportunity includes a stable snapshot-local `id` that can be passed to `/api/explain/:id`.

### `GET /api/alerts`

Returns machine-readable alerts derived from the latest snapshot.

Current alert types include:

- constrained or unhealthy sources
- low executable quote coverage
- large-spread but low-confidence opportunities requiring review

This endpoint is intended for agent notification, monitoring, and future paper-trading automation.

### `GET /api/explain/:id`

Explains an opportunity by `id` or by numeric index:

```text
/api/explain/0
/api/explain/08145fed0ba5f0b7
```

The response includes:

- opportunity details
- related normalized quotes
- confidence
- source mix
- executable related quote count
- caveats
- actionability label

This is the safest endpoint for an agent to call before notifying a user or creating a trade intent.

## Space Agent Integration

Space Agent is useful here, but it should not be part of NASE core.

NASE should remain the deterministic quote engine and API. Space Agent should be an optional workspace and automation layer that consumes NASE API data.

That separation keeps the system clean:

- NASE owns market data, normalization, confidence, and APIs.
- Space Agent owns dashboards, agent prompts, workflows, and operator interaction.
- Any live trading service must be separate from both the browser and NASE collector.

The optional integration pack lives under:

```text
integrations/space-agent/
```

It contains Space Agent customware for:

- a routed `NASE Arbitrage` workspace panel
- a `nase-arbitrage` skill
- a browser helper module that calls NASE through Space Agent's server-side proxy

The helper exposes:

```js
const nase = await import("/mod/nase/arbitrage/ext/skills/nase-arbitrage/nase.js");

await nase.snapshot();
await nase.sources();
await nase.opportunities({ limit: 10, min_confidence: 80 });
await nase.alerts();
await nase.explain("<opportunity-id>");
await nase.executableWethUsdcSanity();
```

### Running Space Agent With The NASE Pack

Clone Space Agent separately. Do not vendor the Space Agent source tree into this repository.

```bash
git clone https://github.com/agent0ai/space-agent.git ../space-agent-nase
cd ../space-agent-nase
npm install
```

Start NASE first:

```bash
cd ../NASE
NASE_WEB_HOST=127.0.0.1 NASE_WEB_PORT=8787 .venv/bin/nase-web
```

Start Space Agent with NASE customware:

```bash
cd ../space-agent-nase
CUSTOMWARE_PATH=../NASE/integrations/space-agent/customware \
SINGLE_USER_APP=true \
LOGIN_ALLOWED=false \
HOST=127.0.0.1 \
PORT=8788 \
node space serve
```

Then open:

```text
http://127.0.0.1:8788/enter?next=%2F%23%2Fnase%2Farbitrage
```

The first page is Space Agent's enter screen. Click `Enter Space` to open the NASE workspace.

## Space Agent Opportunity: Scout And Armed Modes

The strongest use case for Space Agent is not another data source. It is an operator and automation layer.

Recommended stages:

### 1. Scout Mode

Space Agent watches:

- `/api/opportunities`
- `/api/alerts`
- `/api/explain/:id`

It notifies the user when a candidate looks interesting:

- executable related quotes exist
- confidence is high
- source health is acceptable
- spread remains above a configured threshold
- route is on an allowlisted chain and token set

Scout Mode never trades. It explains and alerts.

### 2. Paper Armed Mode

Space Agent keeps a simulated budget and writes a trade journal:

- detected opportunity
- quote sources
- confidence
- estimated gross spread
- estimated fees, gas, and slippage
- assumed fill
- hypothetical PnL
- missed or stale opportunities

This is where thresholds should be tuned before real funds are exposed.

### 3. Live Armed Mode

Live mode should only create signed trade intents through a separate execution service.

Required guardrails:

- max budget per trade
- max daily budget
- max open exposure
- chain allowlist
- token allowlist and denylist
- DEX allowlist
- minimum confidence
- minimum executable depth
- minimum net edge after gas, fees, and slippage
- human confirmation above a threshold
- kill switch
- audit log

Space Agent must not hold private keys in the browser. NASE should not sign transactions. A separate executor should own signing, budget enforcement, and on-chain submission.

## Hardening Work Included In This Proposal

This proposal hardens NASE in three areas: quote quality, operational observability, and integration boundaries. The goal is to make wrong-looking values easier to detect before they are treated as opportunities.

### Source And Quote Hardening

The source layer was expanded so NASE can compare more than one view of the same market:

- aggregator sources for executable or route-aware checks: Jupiter, OpenOcean, LI.FI, Velora / ParaSwap, Odos, KyberSwap, 0x, and 1inch
- chain-specific or venue-specific coverage: Hyperliquid, HyperSwap, and traffic-oriented DEX pool discovery
- broad discovery feeds: DexScreener, DexPaprika, GeckoTerminal-style pools, and LiveCoinWatch where configured

The important distinction is that not every quote has the same strength. NASE now carries that distinction forward instead of flattening every source into one anonymous price:

- `executable` marks quotes that came from a route or quote endpoint rather than passive pool discovery.
- `validation_notes` preserve details such as quote depth, route checks, unsupported chains, missing token addresses, or source-specific constraints.
- source health tracks raw count, normalized count, executable count, success rate, rate-limit state, circuit-breaker state, and wait time.
- API-key-gated sources are explicit in configuration instead of being silently assumed available.

This makes it easier to see when a large spread is real enough to investigate and when it is probably an artifact of stale data, shallow liquidity, missing token mapping, or one weak source.

### Opportunity Hardening

The web API adds stable snapshot-local identifiers for quotes and opportunities. These ids are derived from the opportunity or quote content and let dashboards and agents reference a specific candidate without relying on table position.

The opportunity API supports filtering:

```text
/api/opportunities?limit=25
/api/opportunities?chain=arbitrum
/api/opportunities?min_confidence=80
/api/opportunities?min_spread=0.25
```

This was added so downstream tools can avoid acting on noisy candidates. For example, Space Agent can ask only for high-confidence candidates and then call `/api/explain/:id` before notifying the operator.

### Explainability And Alert Hardening

Two endpoints were added specifically to reduce false confidence:

- `/api/alerts` converts snapshot problems into machine-readable warnings.
- `/api/explain/:id` explains one candidate with related quotes, source mix, executable coverage, caveats, and an actionability label.

Current alert coverage includes:

- sources that are unhealthy, rate-limited, waiting, or circuit-open
- low executable quote coverage across the whole snapshot
- high-spread but low-confidence opportunities that should be manually reviewed

The explain endpoint is intentionally conservative. It does not say "trade this". It tells the caller what supports the candidate, what weakens it, and whether it looks actionable, review-only, or blocked by missing evidence.

### Web Console Hardening

The web console was built as an operator dashboard, not just a visual wrapper:

- source health and quote audit views are first-class screens
- opportunity rows expose confidence, spread, executable related quote count, source count, route, and notes
- refresh state is explicit so a user can tell when data is being collected
- external strings from market data are escaped before rendering in the browser
- mobile table rows collapse into readable card-like records without changing the API payload

Escaping matters because token symbols, DEX labels, and route names come from outside systems. They should be treated as data, not trusted markup.

### Integration Boundary Hardening

The Space Agent work is packaged as an optional integration under `integrations/space-agent/`. It is not placed inside `pipeline/`, `sources/`, or `web/`, and the Space Agent repository is not vendored into NASE.

That boundary is deliberate:

- NASE remains deterministic market-data infrastructure.
- Space Agent remains a consumer for dashboards, scout workflows, and future trade-intent workflows.
- live signing and budget enforcement must live in a separate executor, not in browser customware and not in the NASE collector.

Runtime state produced by Space Agent customware is ignored through `.gitignore`:

```text
integrations/space-agent/customware/L2/
integrations/space-agent/customware/share/
```

This keeps local session data, generated state, and shared runtime files out of commits.

### Verification Hardening

The proposal was verified with code, API, and browser-adjacent checks:

- Python test suite: `.venv/bin/python -m pytest -q`
- Python syntax import sweep: `.venv/bin/python -m compileall -q models pipeline sources tui util web`
- JavaScript syntax checks for the web app and Space Agent helper modules
- whitespace check: `git diff --check`
- live API checks for `/api/sources`, `/api/opportunities`, `/api/alerts`, and `/api/explain/:id`
- Space Agent end-to-end check through both local and Cloudflare-tunneled URLs using the NASE customware path

These checks do not prove a quote is profitable. They prove that the system can collect, expose, explain, and sanity-check the data paths without breaking the app or hiding known uncertainty.

## Quote Reliability Notes

NASE distinguishes broad pool quotes from executable quotes.

Pool-derived quotes are useful for discovery and comparison, but they can be stale, shallow, or non-actionable. Executable quote adapters such as Velora, Odos, and KyberSwap are stronger because they test route depth at notional sizes and add validation notes.

Before treating a candidate as actionable, check:

- `confidence`
- `executable`
- `validation_notes`
- source agreement
- source health
- liquidity
- quote age
- chain gas estimate
- expected slippage

High spread with low confidence is a review candidate, not an execution signal.

## Verification

Common checks:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q models pipeline sources tui util web
node --check web/static/app.js
```

For API checks, after `nase-web` is running:

```bash
curl -sS http://127.0.0.1:8787/api/sources
curl -sS 'http://127.0.0.1:8787/api/opportunities?limit=5'
curl -sS http://127.0.0.1:8787/api/alerts
curl -sS http://127.0.0.1:8787/api/explain/0
```

## Safety

This system surfaces market data and candidate arbitrage routes. It does not guarantee profitability or execution. Real trading requires additional infrastructure for transaction simulation, slippage protection, MEV awareness, signing isolation, and strict budget controls.
