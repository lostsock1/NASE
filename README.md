# NASE — Networked Arbitrage Screener Engine

**Terminal-native cross-chain DEX arbitrage scanner with real-time TUI.**
Pulls live pricing from multiple on-chain data sources, normalizes pairs across
venues, matches arbitrage opportunities, and surfaces actionable spreads — all
inside a keyboard-driven terminal interface.

![Python](https://img.shields.io/badge/python-3.12+-blue)
![Textual](https://img.shields.io/badge/textual-0.80+-purple)
![aiohttp](https://img.shields.io/badge/aiohttp-3.9+-green)
![License](https://img.shields.io/badge/license-MIT-brightgreen)

---

## How It Works

NASE runs a continuous async pipeline on a configurable refresh interval
(default 5 s). Each cycle:

```
┌──────────┐    ┌────────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ COLLECT  │───▶│ NORMALIZE  │───▶│  MATCH   │───▶│   SCAN   │───▶│  FILTER  │
│ 3 APIs   │    │ dedup,     │    │ group by │    │ find      │    │ profit   │
│ parallel │    │ age-check  │    │ base/    │    │ min-ask / │    │ threshold│
│ fetch    │    │ validity   │    │ quote    │    │ max-bid   │    │ dedup    │
└──────────┘    └────────────┘    └──────────┘    └──────────┘    └──────────┘
                                                         │
                                                   gas & bridge
                                                   cost estimation
```

**Collect** — concurrent async fetches from DexScreener, DexPaprika, and
LiveCoinWatch (configurable). Each source runs inside its own rate-limited
session with automatic back-off on 429s.

**Normalize** — validates token addresses, discards stale quotes (older than
2× refresh interval), strips zero/negative prices, deduplicates identical pairs
within each source.

**Match** — groups all quotes by `(base, quote)` symbol pair. A group is
_actionable_ only when it contains at least two distinct (dex, chain) tuples.

**Scan** — within each matched group, identifies the minimum ask and maximum bid,
computes the spread percentage, then subtracts estimated gas (same-chain) or
bridge + gas (cross-chain). Produces an `Opportunity` with net profit in USD
when a capital amount is configured.

**Filter** — applies the minimum-profit threshold, recalculates net profit against
the configured capital, deduplicates by `(pair_address, buy_dex, sell_dex)`, sorts
by spread or net profit, and caps at `max_opportunities`.

---

## Supported Chains

| Chain | Gas Estimate | Comment |
|-------|-------------|---------|
| Ethereum | $8.00 | L1, highest gas |
| Arbitrum | $0.50 | L2 rollup |
| Base | $0.30 | L2 rollup |
| Optimism | $0.30 | L2 rollup |
| Polygon | $0.10 | Sidechain |
| BSC | $0.25 | BNB Smart Chain |
| Avalanche | $0.40 | C-Chain |
| Solana | $0.01 | SVM, lowest fees |

Cross-chain bridge costs are pre-configured for known paths (e.g.
Arbitrum→Ethereum $4.00) and fall back to a default of $10.00 for
unrecognized routes. All estimates are user-adjustable in `config.yaml`.

---

## TUI

```
┌─ NASE v0.1.0 ── 8 chains ── 3 sources ── 5s refresh ────────────┐
│  Capital: $1,000  │  Min Profit: $5.00  │  Sort: profit ▼        │
├──────────────────────────────────────────────────────────────────┤
│  PAIR          SPREAD    BUY DEX     SELL DEX    NET     CHAINS  │
│  WETH/USDC     0.82%     uniswap-v3  pancakeswap  $8.20   eth>bsc│
│  WBTC/USDT     0.45%     orca        raydium      $4.50   sol    │
│  ARB/USDC      0.31%     sushiswap    uniswap-v3  $3.10   arb    │
├──────────────────────────────────────────────────────────────────┤
│  WETH/USDC  │  Buy uniswap-v3 $3,245.12  →  Sell pancakeswap     │
│             │  $3,271.88  │  Spread 0.82%  │  Net $8.20          │
│             │  Sources: dexscreener, dexpaprika                  │
├──────────────────────────────────────────────────────────────────┤
│  dexscreener: OK (87% success)  dexpaprika: OK (92%)             │
│  LCG: OK (24 ref rates)  │  Cycle: 1.2s  │  Pairs: 1,847        │
└──────────────────────────────────────────────────────────────────┘
```

### Keyboard Controls

| Key | Action |
|-----|--------|
| `q` | Quit |
| `c` | Set capital amount in USD (0 to disable profit calc) |
| `d` | Cycle refresh delay: 5 → 15 → 30 → 60 s |
| `s` | Cycle sort column: profit → spread → age → pair |
| `+` / `-` | Adjust minimum profit threshold by $1 |
| `r` | Force immediate refresh cycle |
| `o` | Open selected pair on DexScreener (browser) |
| `Enter` | Show detail panel for selected row |
| `h` | Toggle help overlay |
| `Esc` | Dismiss modal / close help |

---

## Quick Start

### Prerequisites

- Python 3.12+
- API keys (optional — at least one source works without a key):
  - `DEXSCREENER_API_KEY` — DexScreener (free tier available)
  - `DEXPAPRIKA_API_KEY` — DexPaprika
  - `LIVECOINWATCH_API_KEY` — LiveCoinWatch (reference prices)

### Install

```bash
git clone https://github.com/lostsock1/NASE.git
cd NASE
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Configure

Copy the template and add your keys:

```bash
cp .env.example .env      # (create .env.example first if needed)
# Edit .env with your API keys
```

Edit `config.yaml` to adjust chains, gas estimates, refresh interval,
arbitrage types, and source settings. The defaults are sensible for
general-purpose scanning.

### Run

```bash
nase
```

Or directly:

```bash
python main.py
```

The TUI launches immediately and begins cycling. Press `h` for the
on-screen keyboard reference.

---

## Configuration Reference

### `config.yaml`

```yaml
refresh_interval_seconds: 5     # seconds between scan cycles

arb_types:
  simple: true                  # same-chain buy/sell
  triangular: false             # not yet implemented
  cross_chain: false            # not yet implemented

filters:
  min_profit_usd: 5.00          # minimum net profit to surface
  max_opportunities: 100        # max rows in the table

capital:
  amount_usd: 0.0               # 0 = spread-only mode (no net profit)

chain_gas_estimates:            # per-chain gas cost (USD, configurable)
  ethereum: 8.00
  arbitrum: 0.50
  ...

cross_chain_bridge_costs:       # bridge cost overrides (USD)
  arbitrum_to_ethereum: 4.00
  ...

sources:
  dexscreener:
    enabled: true
    max_rps: 5                  # rate limit (requests per second)
    max_concurrent: 3           # concurrent fetches
    timeout_seconds: 30
  dexpaprika:
    enabled: true
    ...
  livecoinwatch:
    enabled: true
    ...
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DEXSCREENER_API_KEY` | No | DexScreener API key |
| `DEXPAPRIKA_API_KEY` | No | DexPaprika API key |
| `LIVECOINWATCH_API_KEY` | No | LiveCoinWatch API key for reference rates |
| `NASE_LOG_LEVEL` | No | Log level (default: `INFO`) |

At least one data source must be enabled and functional. LiveCoinWatch is
optional and provides USD reference rates for the detail panel only.

---

## Architecture

```
nase/
├── main.py                 # entry point
├── config.yaml             # runtime configuration
├── pyproject.toml          # package metadata + dependencies
│
├── models/
│   ├── types.py            # Token, Pair, PriceQuote, Opportunity dataclasses
│   └── constants.py        # known token list, chain normalization
│
├── sources/                # API data sources (each extends Source base)
│   ├── base.py             # abstract Source with rate-limited aiohttp session
│   ├── dexscreener.py      # DexScreener search + normalization
│   ├── dexpaprika.py       # DexPaprika pool discovery
│   └── livecoinwatch.py    # LiveCoinWatch USD reference rates
│
├── pipeline/               # data processing stages
│   ├── collector.py        # parallel fetch orchestration
│   ├── normalizer.py       # address validation, age-based pruning
│   ├── matcher.py          # (base, quote) grouping + actionability check
│   ├── scanner.py          # spread detection + gas/bridge cost calc
│   └── filter.py           # profit thresholding, dedup, sort, cap
│
├── tui/                    # Textual terminal UI layer
│   ├── app.py              # NaseApp — main TUI application + modals
│   ├── header.py           # top bar (version, counts, refresh rate)
│   ├── controls.py         # capital / min-profit / sort controls
│   ├── table.py            # opportunity table with cursor navigation
│   ├── detail.py           # detail panel for selected opportunity
│   └── status.py           # footer with source health + cycle stats
│
└── util/
    ├── config.py           # YAML + env config loading + SourceConfig model
    ├── logging_config.py   # structured logging setup
    └── rate_limiter.py     # aiolimiter-based token bucket
```

### Design Decisions

**Immutable data model.** `Token`, `Pair`, `PriceQuote`, and `Opportunity` are
frozen dataclasses with `__hash__` and `__eq__` implemented on semantically
meaningful keys (lowercased addresses). This prevents accidental mutation in
the pipeline and makes deduplication deterministic.

**Source abstraction.** Each API source extends an abstract `Source` base class
that handles HTTP session lifecycle, rate limiting (via `aiolimiter`), automatic
retry with exponential back-off on 429s, and health reporting. Adding a new data
source is a single-file implementation of `_fetch_impl()`.

**Pipeline composability.** Each pipeline stage is a standalone class with a
single responsibility and no shared mutable state. Stages communicate through
well-typed return values — `PriceQuote` lists → `MatchedGroup` lists →
`Opportunity` lists. This makes the pipeline testable in isolation at each step.

**TUI separation.** The Textual app layer observes pipeline output through
the `_pipeline_data` dict and delegates rendering to specialized widgets.
No business logic lives in the TUI — it's purely a presentation layer.

**Gas-awareness.** Same-chain opportunities subtract chain-specific gas
estimates. Cross-chain opportunities subtract bridge costs plus both
chains' gas. All estimates are user-configurable to reflect real-time
network conditions.

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `textual >= 0.80` | Terminal UI framework |
| `aiohttp >= 3.9` | Async HTTP client for API sources |
| `aiolimiter >= 1.1` | Token-bucket rate limiting |
| `python-dotenv >= 1.0` | `.env` file loading |
| `pyyaml >= 6.0` | `config.yaml` parsing |

No native extensions, no blockchain RPC dependency — NASE runs anywhere
Python 3.12 runs.

---

## Roadmap

- [ ] **Triangular arbitrage** — detect 3-hop paths (A→B, B→C, C→A) across venues
- [ ] **Cross-chain scanning** — bridge-aware multi-hop opportunities
- [ ] **WebSocket sources** — real-time streaming where APIs support it
- [ ] **Price impact modeling** — incorporate pool depth / TVL into profitability
- [ ] **Export** — CSV / JSON output for external analysis
- [ ] **Alerts** — configurable thresholds with desktop notification or webhook

---

## License

MIT — see [LICENSE](LICENSE).
