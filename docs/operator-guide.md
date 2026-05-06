# NASE Operator Guide

This guide explains what NASE is showing, what Space Agent can automate, and what the strategy toggles mean.

NASE is not a trading bot by itself. It is a quote intelligence system. It collects market data, normalizes it, scores confidence, exposes API endpoints, and lets Space Agent watch, explain, paper-test, and draft execution intents.

## Mental Model

NASE has four operational layers:

- Discovery: broad sources identify possible spreads across pairs, chains, and venues.
- Executable quote depth: quote APIs are asked for concrete notional sizes and marked `executable: true` only when they pass validation.
- Space Agent Scout and Paper: the optional workspace filters, alerts, and records paper results.
- Executor boundary: live trading must be handled by a separate service that owns signing, simulation, budgets, and on-chain submission.

Keep those layers separate. Discovery can find an opportunity. Only executable quote depth can support a paper-market replay. Only an executor can prove and submit a real trade.

## Price Types

Not every price means the same thing.

### Discovery Prices

Discovery prices can come from pool data, ticker-like APIs, or recent market activity. They are useful for finding candidates, but they are not proof that a trade can be executed now.

Examples:

- pool midpoint
- last-trade-like prices
- broad DEX screener prices
- venue statistics

These prices can be stale, shallow, or impossible to fill at the shown size. NASE may still use them to spot interesting routes, but Space Agent must not treat them as a paper-trade fill.

### Executable Quote Depth

Executable quote depth means a source returned concrete quote data for a requested notional. NASE validates executable-capable sources across notional checks and marks the result with:

```json
{
  "executable": true,
  "notional_usd": 1000,
  "notes": ["exec_depth:100/1000/10000"]
}
```

Paper-market mode requires both an executable buy leg and an executable sell leg. If either leg is missing, non-executable, or has no positive notional, the paper trade is rejected.

## Space Agent Modes

### Scout Mode

Scout Mode watches:

- `/api/opportunities`
- `/api/alerts`
- `/api/explain/:id`

It can notify the operator when a candidate clears configured thresholds. It does not simulate fills and does not trade.

Useful controls:

- Min Confidence: minimum route confidence.
- Min Spread %: minimum scanner spread before a candidate is interesting.
- Max Age s: maximum quote age tolerated by the scout.
- Min Net $: minimum estimated net edge for paper and intent escalation.

### Paper Armed Mode

Paper Armed Mode writes a paper journal and trade ledger. It is for learning whether a strategy would have looked viable over time, not for proving guaranteed profit.

Paper mode has its own execution strategy:

- `market_exact_in`: default. Replays a trade against executable quote-depth legs for a concrete notional. This is the closest paper mode to reality, but it can still fail in real life because of latency, slippage, MEV, reverts, or stale quotes.
- `limit_hypothesis`: models a limit-order strategy. It is explicitly hypothetical because no order is placed, so NASE cannot know whether it would have filled.

Paper records include:

- `paper_execution_style`
- `execution_evidence`
- `reference_price_kind`
- `fill_certainty`
- `uses_last_trade_price`
- estimated gross edge, fees, gas, slippage, latency haircut, confidence haircut, and net edge

The key rule: market paper can say “quote-time executable.” It cannot say “guaranteed fill.”

### Live Armed Mode

Live Armed Mode in this repo only creates trade-intent drafts. It never signs and never stores private keys.

Live mode has a separate execution strategy:

- `limit_only`: default. The executor must use limit-style execution and reject market fills.
- `hybrid`: the executor tries limit-style execution first and may use market exact-in fallback only after fresh quotes and simulation still clear policy.
- `market_exact_in`: the executor may use market exact-in execution with strict quote TTL, slippage, budget, allowlist, simulation, confirmation, and kill-switch checks.

Every trade intent marks:

- `requires_executor: true`
- `contains_private_key: false`
- `signing_allowed_here: false`

## Strategy Controls

The Space Agent panel exposes these controls:

- Paper Exec: choose `market_exact_in` or `limit_hypothesis` for paper records.
- Live Exec: choose `limit_only`, `hybrid`, or `market_exact_in` for executor intents.
- Live Slip bps: maximum live slippage the executor is allowed to tolerate.
- Quote TTL s: maximum age for executor-side fresh quotes.
- Confirm $: budget threshold above which human confirmation is required.
- Paper Budget: simulated budget for paper records.
- Max Trade: maximum budget per trade.
- Min Net $: minimum expected net edge after costs.

## Recommended Workflow

Start conservatively:

1. Run NASE and Space Agent with Docker.
2. Enable Scout Mode only.
3. Watch source health and executable quote coverage.
4. Enable Paper Armed Mode with `market_exact_in`.
5. Let the ledger collect enough samples.
6. Review rejected candidates and warnings.
7. Compare `market_exact_in` paper records with optional `limit_hypothesis` records.
8. Only then consider Live Armed Mode, and only with a separate executor.

## Docker Quick Start

From the repo root:

```bash
docker compose up --build
```

Open:

```text
http://127.0.0.1:8787
http://127.0.0.1:8788/enter?next=%2F%23%2Fnase%2Farbitrage
```

To use different published ports:

```bash
NASE_WEB_PORT_PUBLISHED=18877 SPACE_AGENT_PORT_PUBLISHED=18878 docker compose up --build
```

## Safety Boundary

Do not put private keys in Space Agent browser customware.

Do not make NASE sign transactions.

A live executor must own:

- signer isolation
- budget vault
- allowlists and denylists
- transaction simulation
- fresh quote checks
- quote TTL enforcement
- slippage enforcement
- human confirmation threshold
- kill switch
- audit log

If an executor cannot satisfy the intent guardrails, it should reject the intent.

## Executor Service

This proposal now includes a first executor boundary. It is still dry-run by default, but it is useful because it validates a Space Agent trade intent against fresh NASE data and writes an audit record.

The executor runs separately from Space Agent:

```text
http://127.0.0.1:8790
```

Space Agent can send a drafted intent to:

- `POST /api/intents/validate`
- `POST /api/intents/submit`

The executor then fetches fresh `/api/explain/:id`, checks executable legs, quote TTL, notional, price bounds, budget limits, and human confirmation. If anything fails, it returns `rejected`. If everything passes while live trading is disabled, it returns `accepted_dry_run`.

For the endpoint details and safety model, see:

```text
docs/executor.md
```
