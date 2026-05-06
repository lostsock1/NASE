# NASE Executor

The NASE executor is a separate service for trade-intent validation and audit logging.

It is intentionally not part of Space Agent browser customware. Space Agent can draft an intent, but the executor is the first server-side boundary that can re-check whether an intent is still actionable.

Current scope:

- accept a trade-intent draft
- fetch a fresh `/api/explain/:id` payload from NASE
- require executable buy and sell legs
- enforce quote TTL, notional, price bounds, budgets, and confirmation flags
- write an audit ledger
- return `accepted_dry_run` or `rejected`

Out of scope for this version:

- private keys
- signing
- on-chain submission
- live order placement
- MEV protection
- nonce management

Live trading is disabled by default through:

```text
NASE_EXECUTOR_LIVE_TRADING_ENABLED=false
```

Even if this is changed later, a signer adapter still has to enforce vault, chain, token, DEX, kill-switch, and simulation policy.

## Endpoints

### `GET /health`

Returns service status and whether live trading is enabled.

### `POST /api/intents/validate`

Validates an intent without writing an audit submission.

Payload:

```json
{
  "intent": {
    "id": "intent-id",
    "opportunity_id": "opportunity-id"
  },
  "human_confirmed": false
}
```

The service fetches fresh NASE data by `opportunity_id` unless `fresh_explain` is included explicitly.

### `POST /api/intents/submit`

Runs the same validation and writes a JSONL audit record. In the default configuration this is still dry-run only.

### `GET /api/ledger`

Returns the latest audit records.

## Docker

`docker compose up --build` starts:

- `nase-web` on port `8787`
- `space-agent` on port `8788`
- `nase-executor` on port `8790`

Space Agent receives the Docker-internal executor URL through `docker/space-agent-nase-config.js`.

## Decision Statuses

- `rejected`: one or more hard checks failed.
- `accepted_dry_run`: all hard checks passed, but live trading is disabled.
- `accepted_executor_ready`: checks passed and live trading is enabled; a future signer adapter may continue from here.

Returned decisions always include:

- `submitted: false`
- `signed: false`
- `broadcast: false`

Those flags should remain false until a real signer and transaction broadcaster exist.

## Safety Checks

The executor rejects intents when:

- the intent is not `intent_requires_executor`
- private key material is present
- browser-side signing is allowed
- the live execution style is not allowlisted
- executable legs are missing
- fresh NASE explain data is missing
- quote age exceeds `quote_ttl_seconds`
- fresh notional is below budget
- fresh spread is non-positive
- buy or sell prices violate the intent bounds
- human confirmation is required but not provided
- per-trade or daily budget would be exceeded

This makes the executor useful immediately as a guard and audit layer, even before real trading is added.
