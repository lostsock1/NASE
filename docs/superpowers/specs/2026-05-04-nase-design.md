# NASE — Design Specification

## 1. Overview

**NASE** is a local-only, terminal-based, read-only arbitrage screener. It asynchronously fetches price data from multiple free-tier DEX APIs, normalizes ask/bid prices into a unified model, matches identical token pairs across different DEXes, computes profitable spreads, and displays live opportunities in a terminal dashboard. NASE never signs transactions, never connects to a wallet, and never interacts with any blockchain.

## 2. Technology Stack

| Concern | Choice | Rationale |
|---------|--------|-----------|
| Language | Python 3.12+ | Lowest learning curve for a non-programmer; async-native; richest crypto library ecosystem |
| Async framework | `asyncio` + `aiohttp` | I/O-bound workload; thousands of concurrent HTTP fetches without threads |
| TUI | `textual` | First-class terminal dashboard framework; sortable tables, live refresh, keyboard shortcuts |
| Rate limiting | `aiolimiter` | Token-bucket per source; prevents tripping free-tier API limits while saturating available bandwidth |
| Config (secrets) | `python-dotenv` + `.env` file | Never committed to git |
| Config (behavior) | PyYAML + `config.yaml` | Structured, version-controlled; per-source rate limits, refresh intervals, thresholds |
| Data model | `dataclasses` | Lightweight, typed, no external ORM dependency |
| Price arithmetic | `decimal.Decimal` | Avoids floating-point rounding on financial calculations |
| HTTP client | `aiohttp.ClientSession` (reused) | Connection pooling across cycles; DNS caching; TCP keep-alive |

## 3. Project Structure

```
NASE/
├── main.py                 # Entry point: CLI args, config loader, TUI launcher
├── config.yaml             # Behavior settings (rate limits, thresholds, chains)
├── .env                    # API keys (never committed)
├── pipeline/
│   ├── collector.py        # Orchestrates all sources concurrently
│   ├── normalizer.py       # Raw API JSON -> List[PriceQuote]
│   ├── matcher.py          # Groups quotes by (chain, base, quote)
│   ├── scanner.py          # Simple / triangular / cross-chain arb computation
│   └── filter.py           # Threshold application, dedup, sort
├── sources/
│   ├── base.py             # Abstract base: Source ABC
│   ├── dexscreener.py      # DexScreener API integration
│   ├── dexpaprika.py       # DexPaprika API integration
│   └── swapapi.py          # SwapAPI integration
├── models/
│   ├── types.py            # Token, Pair, PriceQuote, Opportunity
│   └── constants.py        # Chain IDs, address formats, token seed list
├── tui/
│   ├── app.py              # Textual App subclass
│   ├── header.py           # Header bar widget (cycle time, counts)
│   ├── controls.py         # Control bar widget (toggles, capital, threshold)
│   ├── table.py            # Main opportunity table widget
│   ├── detail.py           # Detail panel widget (expanded on Enter)
│   └── status.py           # Status bar widget (source health, chain stats)
├── util/
│   ├── rate_limiter.py     # TokenBucket class per source
│   ├── config.py           # Config + .env loader and validator
│   └── logging_config.py   # Structured logging setup
└── pyproject.toml          # Dependencies, project metadata
```

## 4. Source Integrations

### 4.1 DexScreener

- **Free tier:** Yes. No API key required for basic endpoints. Rate limit ~300 req/min observed, but we conservatively default to 5 req/s.
- **Endpoint:** `GET /latest/dex/search?q={tokenSymbol}` — returns all pairs containing that token across all chains.
- **Discovery strategy:** Seed with top 100 tokens per chain (from `constants.py` token list). Search each token. Deduplicate returned pairs by `pairAddress`. Cache discovered pair addresses to avoid re-searching known tokens.
- **Response mapping -> PriceQuote:** `priceUsd` -> ask_price (no native bid/ask in free tier — use `priceUsd` as both with a small spread estimate), `liquidity.usd`, `volume.h24`, `pairAddress`, `baseToken.symbol`/`address`, `quoteToken.symbol`/`address`, `chainId`.
- **Limitation:** Free DexScreener doesn't expose orderbook ask/bid. We use `priceUsd` as mid-price and estimate spread from `priceChange.h24` volatility. The pair detail pane shows the DexScreener URL so you can click through for live orderbook data.

### 4.2 DexPaprika

- **Free tier:** Yes. API key optional (adds higher limits). Without key: rate limit TBD (we default to 10 req/s observed generous).
- **Endpoints:**
  - `GET /networks/{chain}/pools` — paginated pool list per chain with addresses
  - `GET /networks/{chain}/pools/{pool_address}` — single pool details including price
- **Discovery strategy:** Paginate all pools per chain. Each page returns up to 100 pools. Cache pool addresses between cycles; only fetch new pools discovered since last cycle.
- **Response mapping -> PriceQuote:** Pool detail returns `price` (true ask), `volume_usd`, `liquidity_usd`, `token0`/`token1` addresses and symbols.

### 4.3 SwapAPI

- **Free tier:** Yes. Requires API key.
- **Endpoints:**
  - `GET /tokens?network={chain}` — token list
  - `POST /prices` — bulk price lookup: `{"tokens": [{"address": "...", "network": "..."}]}`
- **Discovery strategy:** Fetch token list per chain once per session, poll `/prices` in bulk each cycle. The `/prices` endpoint returns both ask and bid prices where available.
- **Response mapping -> PriceQuote:** `price`/`ask`/`bid` fields, token address, network. This is the strongest source for true bid/ask data.

## 5. Pipeline Stages

### 5.1 Collector

```python
async def collect(sources: list[Source], config: Config) -> dict[str, list[dict]]:
    """Fire all sources concurrently. Return raw JSON keyed by source name."""
    tasks = [source.fetch(config) for source in sources]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    output = {}
    for source, result in zip(sources, results):
        if isinstance(result, Exception):
            log.error(f"{source.name}: {result}")
            output[source.name] = []  # Empty, source marked unhealthy
        else:
            output[source.name] = result
    return output
```

**Health:** If a source raises, its result is replaced with an empty list. The source is marked `X` in the TUI status bar. The pipeline continues with remaining sources. After 3 consecutive failures, the source is paused for 60 seconds (cool-down) to avoid hammering a down API.

**Rate limit exhaustion:** The `TokenBucket` class raises `RateLimitedError` when tokens are depleted. The collector catches this per-source and displays the countdown to next available token slot in the status bar (e.g., `SwapAPI <clock> 4s`).

### 5.2 Normalizer

Each source has a dedicated normalizer function:

```python
def normalize_dexscreener(raw: dict) -> list[PriceQuote]:
    """Convert DexScreener search response -> PriceQuote list."""
    pairs = raw.get("pairs", [])
    quotes = []
    for p in pairs:
        try:
            quotes.append(PriceQuote(
                pair=Pair(
                    base=Token(address=p["baseToken"]["address"], symbol=p["baseToken"]["symbol"],
                               chain=_normalize_chain(p["chainId"]), decimals=18),
                    quote=Token(address=p["quoteToken"]["address"], symbol=p["quoteToken"]["symbol"],
                                chain=_normalize_chain(p["chainId"]), decimals=18),
                    pair_address=p["pairAddress"],
                ),
                dex=p.get("dexId", "unknown"),
                source_api="dexscreener",
                ask_price=Decimal(str(p.get("priceUsd", 0))),
                bid_price=Decimal(str(p.get("priceUsd", 0))),
                liquidity_usd=float(p.get("liquidity", {}).get("usd", 0)),
                volume_24h_usd=float(p.get("volume", {}).get("h24", 0)),
                fetched_at=time.time(),
            ))
        except (KeyError, TypeError, DecimalException):
            continue  # Skip malformed entries
    return quotes
```

**Chain name normalization:** Every source uses different chain identifiers (e.g., DexScreener: `"ethereum"`, DexPaprika: `"eth"`, SwapAPI: `1`). The normalizer maps all to a canonical name (`"ethereum"`) using a lookup table in `constants.py`.

**Validation:** A `PriceQuote` is dropped if:
- `ask_price` or `bid_price` is zero or negative
- Token address is not a valid hex string
- `fetched_at` is older than 2x the configured `refresh_interval`

### 5.3 Matcher

```python
def match(all_quotes: list[PriceQuote], arb_types: set[str]) -> list[MatchedGroup]:
```

Groups quotes by the composite key `(chain, base_address, quote_address)`.

A group is **actionable** if it contains >=2 quotes from different DEXes. This is the minimum requirement for cross-DEX arbitrage.

For **cross-chain matching**, re-group by `(base_address, quote_address)` ignoring chain — actionable if >=2 quotes from different chains exist.

For **triangular arb**, the matcher extracts all same-chain pairs and passes them to the scanner's graph engine.

### 5.4 Scanner

Three scan modes, each independently togglable:

**Simple (Cross-DEX, same chain):**
```
For each matched group:
    lowest_ask = min(quotes, key=lambda q: q.ask_price)
    highest_bid = max(quotes, key=lambda q: q.bid_price)
    if lowest_ask.dex != highest_bid.dex:
        spread_pct = ((highest_bid.bid_price - lowest_ask.ask_price) / lowest_ask.ask_price) * 100
```

**Triangular (same chain):**
Graph search over all same-chain pairs. For each pair A/B and B/C, look for pair A/C. If cycle product > 1.0 + epsilon, there's a triangular arb. Limited to same-chain triples to bound complexity.

```
For triples (a->b, b->c, a->c):
    rate_ab = 1 / a_ask_in_b  # buying b with a
    rate_bc = 1 / b_ask_in_c  # buying c with b
    rate_ca = c_bid_in_a      # selling c for a
    product = rate_ab * rate_bc * rate_ca
    if product > 1.0:
        spread_pct = (product - 1.0) * 100
```

**Cross-chain (different chains):**
For each token pair that exists on >=2 chains, compare best price per chain.

```
For each (base, quote) across chains:
    Profit = price_on_chain_A x capital - estimated_bridge_fee - price_on_chain_B x capital
```

Bridge fees are a flat config value per chain pair (e.g., `arbitrum->ethereum: $4.00`), estimated conservatively from typical L2->L1 costs.

### 5.5 Filter

```python
def filter_opportunities(
    opportunities: list[Opportunity],
    min_profit_usd: float,
    capital: float | None,
) -> list[Opportunity]:
```

1. If `capital` is set, recalculate `net_profit_usd` for each opportunity using the capital amount.
2. Drop all opportunities where `net_profit_usd < min_profit_usd`.
3. Deduplicate: when two APIs confirm the same pair/DEX combination with prices within 1%, merge into one row with a `confirmed_by: [2 sources]` badge. When prices disagree by >2%, show the more conservative (lower profit) version.
4. Sort by: configurable column (default: net_profit_usd descending).
5. Return top N (configurable, default 100) to keep the TUI scrollable.

## 6. Data Fetching — Core Architecture

### 6.1 Rate Limiter

```python
class TokenBucket:
    """Token bucket rate limiter for asyncio."""

    def __init__(self, rate: float, burst: int = 1):
        self.rate = rate          # tokens per second
        self.burst = burst        # max burst tokens
        self._tokens = burst
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self):
        """Wait until a token is available, then consume one."""
        async with self._lock:
            while self._tokens < 1:
                await asyncio.sleep(1 / self.rate)
                self._refill()
            self._tokens -= 1

    async def available_in(self) -> float:
        """Seconds until next token is available. For status display."""
        ...
```

Each source wraps its HTTP calls:

```python
class DexScreenerSource(Source):
    def __init__(self, config):
        self._semaphore = asyncio.Semaphore(config.max_concurrent)
        self._bucket = TokenBucket(config.max_rps)

    async def _get(self, session, url):
        await self._bucket.acquire()
        async with self._semaphore:
            return await session.get(url)
```

**Status reporting:** The `TokenBucket.available_in()` method is polled before display to show countdown timers in the TUI.

### 6.2 HTTP Session Pooling

One `aiohttp.ClientSession` per source, created at startup, reused for the entire session lifetime. Each session gets:
- Connection pool limit = `max_concurrent`
- TCP keep-alive enabled
- DNS cache enabled (via `aiohttp`'s `TCPConnector`)
- Timeout: `aiohttp.ClientTimeout(total=30)` per request

### 6.3 Cycle Execution

```python
async def run_cycle(sources, config):
    while True:
        cycle_start = time.monotonic()

        raw_data = await collector.collect(sources, config)
        quotes = normalizer.normalize_all(raw_data, config)
        groups = matcher.match(quotes, config.enabled_arb_types)
        opps = scanner.scan(groups, config)
        filtered = filter.filter_opportunities(opps, config)

        await tui.update(filtered, source_status)

        elapsed = time.monotonic() - cycle_start
        sleep_for = max(0, config.refresh_interval - elapsed)
        await asyncio.sleep(sleep_for)
```

**No backpressure:** If a cycle takes longer than `refresh_interval`, the next cycle starts immediately (sleep duration is 0). The TUI shows the actual cycle time in the header.

## 7. TUI Dashboard

### 7.1 Layout

```
┌─ NASE v0.1 ──── Cycle: 3.2s ──── Pairs: 12,847 ──── Opportunities: 4 ── [q] quit ─┐
│                                                                                       │
│  ARB: [SIMPLE] [TRI] [CROSS]    CAPITAL: $1,000    MIN PROFIT: $5.00               │
│                                                                                       │
│  ┌───────────────────────────────────────────────────────────────────────────────┐   │
│  │  # │ Pair         │ Buy At       │ Sell At      │ Spread │ Profit │ Age │ Ch │   │
│  │────┼──────────────┼──────────────┼──────────────┼────────┼────────┼─────┼────│   │
│  │ 1  │ WETH/USDC    │ Uniswap V3   │ SushiSwap    │ 2.14%  │ $21.40 │ 3s  │ ET │   │
│  │ 2  │ WBTC/WETH    │ Curve        │ Balancer     │ 0.87%  │ $8.70  │ 5s  │ AR │   │
│  │ 3  │ ARB/USDC     │ Camelot      │ Uniswap V3   │ 1.42%  │ $14.20 │ 8s  │ AR │   │
│  │ 4  │ LINK/WETH    │ Uniswap V3   │ Uniswap V2   │ 0.45%  │ $4.50  │ 2s  │ ET │   │
│  └───────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                       │
│  SOURCES: DexScreener ✓  DexPaprika ✓  SwapAPI <clock> 4s                                 │
│  CHAINS:  ethereum(4,231) arbitrum(3,109) base(2,844) optimism(1,612)              │
│                                                                                       │
│  ┌─ Details: WETH/USDC ──────────────────────────────────────────────────────────┐   │
│  │  Uniswap V3           ASK: $3,001.42    24h Vol: $14.2M    Liq: $8.3M [DS][DP]│   │
│  │  SushiSwap            BID: $3,065.60    24h Vol: $2.1M     Liq: $1.1M [DS]    │   │
│  │  Spread: 2.14%    Gross: $64.18    Gas Est: $8.00    Net: $56.18              │   │
│  │  Capital $1,000 -> Output: $1,021.40 -> Net after gas: $13.40                   │   │
│  │  Sources: [DS] DexScreener  [DP] DexPaprika                                     │   │
│  └───────────────────────────────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────────────────────────────┘
```

### 7.2 Keyboard Controls

| Key | Action |
|-----|--------|
| `q` | Quit |
| `a` | Cycle arb type toggle: SIMPLE -> TRI -> CROSS -> ALL -> SIMPLE |
| `s` | Cycle sort column: Net Profit -> Spread % -> Age -> Pair Name |
| `up` `down` | Move row selection |
| `Enter` | Expand/collapse detail panel for selected row |
| `+` / `-` | Increase/decrease `min_profit_usd` by $1 (shift: by $10) |
| `c` | Enter capital mode — type amount + Enter to set. Type `0` to disable. |
| `r` | Force immediate refresh (skip sleep) |
| `h` | Toggle help overlay |
| `1-9` | Switch to tab N (future: per-chain tabs) |

### 7.3 Color Scheme

| Element | Color | Meaning |
|---------|-------|---------|
| Source ✓ | Green bold | Healthy, returning data |
| Source ✗ | Red bold | Failed, no data returned |
| Source <clock> | Yellow | Rate-limited, waiting for slot |
| Spread >= 2% | Green | Strong opportunity |
| Spread 1-2% | Yellow | Moderate |
| Spread < 1% | Dim | Marginal |
| 2+ source confirmation | Green badge | High confidence |
| 1 source only | Yellow badge | Single source, verify |
| Price >15s old | Red age text | Stale data |

**No mock data. No dummy rows.** The table is empty on startup. Rows populate only when real API data produces real opportunities. The status bar shows live source health and API rate-limit countdowns. If all sources fail, the table stays empty and the status bar tells you why.

## 8. Configuration

### 8.1 `config.yaml`

```yaml
# NASE Configuration

refresh_interval_seconds: 5

arb_types:
  simple: true
  triangular: false
  cross_chain: false

filters:
  min_profit_usd: 5.00
  max_opportunities: 100

capital:
  amount_usd: 0.0          # 0 = disabled (show gross spread)

chain_gas_estimates:
  ethereum: 8.00
  arbitrum: 0.50
  base: 0.30
  optimism: 0.30
  polygon: 0.10
  bsc: 0.25
  avalanche: 0.40
  solana: 0.01

cross_chain_bridge_costs:
  arbitrum_to_ethereum: 4.00
  base_to_ethereum: 2.00
  optimism_to_ethereum: 2.00
  polygon_to_ethereum: 3.00

sources:
  dexscreener:
    enabled: true
    base_url: "https://api.dexscreener.io"
    max_rps: 5
    max_concurrent: 3
    timeout_seconds: 30
  dexpaprika:
    enabled: true
    base_url: "https://api.dexpaprika.com"
    max_rps: 10
    max_concurrent: 5
    timeout_seconds: 30
  swapapi:
    enabled: true
    base_url: "https://swapapi.io/api/v1"
    max_rps: 3
    max_concurrent: 2
    timeout_seconds: 30

chains:
  - ethereum
  - arbitrum
  - base
  - optimism
  - polygon
  - bsc
  - avalanche
  - solana
```

### 8.2 `.env`

```bash
# NASE API Keys
DEXSCREENER_API_KEY=           # Optional; free tier works without
DEXPAPRIKA_API_KEY=            # Optional; increases rate limits
SWAPAPI_API_KEY=               # Required
```

Configuration is validated at startup. Invalid values (negative refresh interval, unknown chain names, conflicting toggle states) produce clear error messages and halt before any HTTP call is made.

## 9. Extensibility — Adding a New Source

Adding a new DEX data source requires exactly **2 files and 1 config entry**:

1. **`sources/newdex.py`** — subclass `Source` ABC:

```python
from sources.base import Source
from models.types import PriceQuote

class NewDexSource(Source):
    name = "newdex"
    base_url: str

    async def fetch(self, config) -> list[PriceQuote]:
        ...

    def normalize(self, raw: dict) -> list[PriceQuote]:
        ...
```

2. **Add to `config.yaml`:**
```yaml
sources:
  newdex:
    enabled: true
    base_url: "https://api.newdex.com"
    max_rps: 5
    max_concurrent: 3
    timeout_seconds: 30
```

3. **Register in `pipeline/collector.py`** — add one line to the source list.

The pipeline (normalizer, matcher, scanner, filter) is source-agnostic. It operates on the `PriceQuote` model. No pipeline code changes when adding a source.

Similarly, adding a new arb strategy: write one function in `scanner.py` that takes `list[MatchedGroup]` and returns `list[Opportunity]`. Register it in config with a toggle.

## 10. Logging & Debugging

Structured JSON-line logging to `nase.log`:

```json
{"ts": "2026-05-04T10:23:01.123Z", "level": "INFO", "source": "dexscreener", "event": "fetch_complete", "pairs": 1423, "duration_ms": 320}
{"ts": "2026-05-04T10:23:01.456Z", "level": "WARN", "source": "swapapi", "event": "rate_limited", "retry_after_ms": 4000}
{"ts": "2026-05-04T10:23:02.789Z", "level": "INFO", "event": "cycle_complete", "total_pairs": 12847, "opportunities": 4, "duration_ms": 2100}
{"ts": "2026-05-04T10:23:03.001Z", "level": "ERROR", "source": "dexpaprika", "event": "http_error", "status": 503, "url": "..."}
```

The log file is append-only. Rotate manually when it grows large. Debug level (`NASE_LOG_LEVEL=DEBUG` in `.env`) adds per-request HTTP traces.

## 11. Startup Flow

1. Load `.env` -> load `config.yaml` -> validate both
2. Validate that at least one source is enabled
3. Validate that at least one chain is configured
4. Validate that at least one arb type is enabled
5. Initialize `aiohttp.ClientSession` per source
6. Create source instances with their rate limiters
7. Launch `textual` TUI application
8. TUI's `on_mount` event triggers the first `run_cycle()`
9. Cycles continue until user presses `q`

## 12. Exit & Cleanup

On `q`:
1. Cancel running async tasks
2. Close all `aiohttp.ClientSession`s (releases TCP connections)
3. Flush log buffer
4. Print summary to stdout: `"Session: 45 cycles, 12,847 avg pairs, 4 max opportunities"`
5. Exit code 0

## 13. What NASE Does NOT Do

- No on-chain RPC calls
- No wallet integration
- No transaction signing or sending
- No keystore or private key storage
- No database persistence
- No mock/dummy/test data
- No web UI
- No network access beyond configured API endpoints
- No automated trading — ever

## 14. Dependencies (`pyproject.toml`)

```toml
[project]
name = "nase"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "aiohttp>=3.9",
    "aiolimiter>=1.1",
    "textual>=0.80",
    "python-dotenv>=1.0",
    "pyyaml>=6.0",
]
```
