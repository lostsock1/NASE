# NASE Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local-only, terminal-based DEX arbitrage screener that concurrently fetches prices from DexScreener, DexPaprika, and SwapAPI, computes spreads, and displays live opportunities in a Textual TUI.

**Architecture:** Pipeline architecture with four stages (collect -> normalize -> match -> scan -> filter). Each DEX source is an isolated class implementing a Source ABC. Sources fire concurrently via `asyncio.gather`, each with its own token-bucket rate limiter. The TUI layer subscribes to pipeline results and renders a sortable table with live health indicators.

**Tech Stack:** Python 3.12+, asyncio, aiohttp, aiolimiter, textual, python-dotenv, PyYAML, decimal module.

---

### Task 1: Project Scaffold

**Files:**
- Create: `NASE/pyproject.toml`
- Create: `NASE/.gitignore`

- [ ] **Step 1: Write pyproject.toml**

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

[project.scripts]
nase = "main:main"
```

- [ ] **Step 2: Write .gitignore**

```
.env
nase.log
__pycache__/
*.pyc
.venv/
venv/
```

- [ ] **Step 3: Create all empty directory structure**

Run:
```bash
mkdir -p NASE/{pipeline,sources,models,tui,util}
```

- [ ] **Step 4: Install dependencies**

```bash
cd NASE && pip install -e "."
```

- [ ] **Step 5: Verify Python version**

```bash
python --version
```
Expected: Python 3.12.x or higher

- [ ] **Step 6: Commit**

```bash
cd NASE && git init && git add -A && git commit -m "feat: project scaffold with pyproject.toml"
```

---

### Task 2: Data Models

**Files:**
- Create: `NASE/models/__init__.py`
- Create: `NASE/models/types.py`
- Create: `NASE/models/constants.py`

- [ ] **Step 1: Write models/__init__.py**

```python
from models.types import Token, Pair, PriceQuote, Opportunity
from models.constants import CHAIN_ALIASES, KNOWN_TOKENS

__all__ = ["Token", "Pair", "PriceQuote", "Opportunity", "CHAIN_ALIASES", "KNOWN_TOKENS"]
```

- [ ] **Step 2: Write models/types.py**

```python
from dataclasses import dataclass, field
from decimal import Decimal
import time


@dataclass(frozen=True)
class Token:
    address: str
    symbol: str
    chain: str
    decimals: int = 18

    def __hash__(self) -> int:
        return hash((self.address.lower(), self.chain))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Token):
            return NotImplemented
        return self.address.lower() == other.address.lower() and self.chain == other.chain


@dataclass(frozen=True)
class Pair:
    base: Token
    quote: Token
    pair_address: str

    @property
    def chain(self) -> str:
        return self.base.chain

    def __hash__(self) -> int:
        return hash(self.pair_address.lower())

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Pair):
            return NotImplemented
        return self.pair_address.lower() == other.pair_address.lower()


@dataclass(frozen=True, slots=True)
class PriceQuote:
    pair: Pair
    dex: str
    source_api: str
    ask_price: Decimal
    bid_price: Decimal
    liquidity_usd: float = 0.0
    volume_24h_usd: float = 0.0
    fetched_at: float = field(default_factory=time.time)

    @property
    def mid_price(self) -> Decimal:
        return (self.ask_price + self.bid_price) / Decimal("2")

    @property
    def age_seconds(self) -> float:
        return time.time() - self.fetched_at


@dataclass(frozen=True, slots=True)
class Opportunity:
    pair: Pair
    buy_at_dex: str
    sell_at_dex: str
    buy_price: Decimal
    sell_price: Decimal
    spread_pct: float
    net_profit_usd: float
    source_apis: list[str] = field(default_factory=list)
    detected_at: float = field(default_factory=time.time)

    @property
    def age_seconds(self) -> float:
        return time.time() - self.detected_at
```

- [ ] **Step 3: Write models/constants.py**

```python
CHAIN_ALIASES: dict[str, str] = {
    "ethereum": "ethereum",
    "eth": "ethereum",
    "1": "ethereum",
    "ether": "ethereum",
    "arbitrum": "arbitrum",
    "arb": "arbitrum",
    "42161": "arbitrum",
    "arbitrum one": "arbitrum",
    "base": "base",
    "8453": "base",
    "optimism": "optimism",
    "op": "optimism",
    "10": "optimism",
    "optimistic ethereum": "optimism",
    "polygon": "polygon",
    "matic": "polygon",
    "137": "polygon",
    "polygon pos": "polygon",
    "bsc": "bsc",
    "bnb": "bsc",
    "56": "bsc",
    "binance smart chain": "bsc",
    "binance": "bsc",
    "avalanche": "avalanche",
    "avax": "avalanche",
    "43114": "avalanche",
    "avalanche c-chain": "avalanche",
    "solana": "solana",
    "sol": "solana",
}


def normalize_chain(raw: str) -> str:
    key = raw.strip().lower()
    return CHAIN_ALIASES.get(key, key)


KNOWN_TOKENS: dict[str, list[dict[str, str]]] = {
    "ethereum": [
        {"address": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "symbol": "WETH", "decimals": "18"},
        {"address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", "symbol": "USDC", "decimals": "6"},
        {"address": "0xdAC17F958D2ee523a2206206994597C13D831ec7", "symbol": "USDT", "decimals": "6"},
        {"address": "0x6B175474E89094C44Da98b954EedeAC495271d0F", "symbol": "DAI", "decimals": "18"},
        {"address": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599", "symbol": "WBTC", "decimals": "8"},
        {"address": "0x514910771AF9Ca656af840dff83E8264EcF986CA", "symbol": "LINK", "decimals": "18"},
        {"address": "0x7D1AfA7B718fb893dB30A3aBc0Cfc608AaCfeBB0", "symbol": "MATIC", "decimals": "18"},
        {"address": "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984", "symbol": "UNI", "decimals": "18"},
        {"address": "0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84", "symbol": "stETH", "decimals": "18"},
        {"address": "0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0", "symbol": "wstETH", "decimals": "18"},
    ],
    "arbitrum": [
        {"address": "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1", "symbol": "WETH", "decimals": "18"},
        {"address": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831", "symbol": "USDC", "decimals": "6"},
        {"address": "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9", "symbol": "USDT", "decimals": "6"},
        {"address": "0xDA10009cBd5D07dd0CeCc66161FC93D7c9000da1", "symbol": "DAI", "decimals": "18"},
        {"address": "0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f", "symbol": "WBTC", "decimals": "8"},
        {"address": "0xf97f4df75117a78c1A5a0DBb814Af92458539FB4", "symbol": "LINK", "decimals": "18"},
        {"address": "0x912CE59144191C1204E64559FE8253a0e49E6548", "symbol": "ARB", "decimals": "18"},
    ],
    "base": [
        {"address": "0x4200000000000000000000000000000000000006", "symbol": "WETH", "decimals": "18"},
        {"address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "symbol": "USDC", "decimals": "6"},
        {"address": "0xd9aAEc86B65D86f6A7B5B1b0c42FFA531710b6CA", "symbol": "USDbC", "decimals": "6"},
        {"address": "0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb", "symbol": "DAI", "decimals": "18"},
    ],
    "optimism": [
        {"address": "0x4200000000000000000000000000000000000006", "symbol": "WETH", "decimals": "18"},
        {"address": "0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85", "symbol": "USDC", "decimals": "6"},
        {"address": "0x94b008aA00579c1307B0EF2c499aD98a8ce58e58", "symbol": "USDT", "decimals": "6"},
        {"address": "0xDA10009cBd5D07dd0CeCc66161FC93D7c9000da1", "symbol": "DAI", "decimals": "18"},
    ],
    "polygon": [
        {"address": "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619", "symbol": "WETH", "decimals": "18"},
        {"address": "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359", "symbol": "USDC", "decimals": "6"},
        {"address": "0xc2132D05D31c914a87C6611C10748AEb04B58e8F", "symbol": "USDT", "decimals": "6"},
        {"address": "0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063", "symbol": "DAI", "decimals": "18"},
        {"address": "0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6", "symbol": "WBTC", "decimals": "8"},
    ],
    "bsc": [
        {"address": "0x2170Ed0880ac9A755fd29B2688956BD959F933F8", "symbol": "WETH", "decimals": "18"},
        {"address": "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d", "symbol": "USDC", "decimals": "18"},
        {"address": "0x55d398326f99059fF775485246999027B3197955", "symbol": "USDT", "decimals": "18"},
        {"address": "0x1AF3F329e8BE154074D8769D1FFa4eE058B1DBc3", "symbol": "DAI", "decimals": "18"},
        {"address": "0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c", "symbol": "WBTC", "decimals": "18"},
        {"address": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c", "symbol": "WBNB", "decimals": "18"},
    ],
    "avalanche": [
        {"address": "0x49D5c2BdFfac6CE2BFdB6640F4F80f226bc10bAB", "symbol": "WETH.e", "decimals": "18"},
        {"address": "0xB97EF9Ef8734C71904D8002F8b6Bc66Dd9c48a6E", "symbol": "USDC", "decimals": "6"},
        {"address": "0x9702230A8Ea53601f5cD2dc00fDBc13d4dF4A8c7", "symbol": "USDT", "decimals": "6"},
        {"address": "0xd586E7F844cEa2F87f50152665BCbc2C279D8d70", "symbol": "DAI.e", "decimals": "18"},
        {"address": "0xB31f66AA3C1e785363F0875A1B74E27b85FD66c7", "symbol": "WAVAX", "decimals": "18"},
    ],
    "solana": [
        {"address": "So11111111111111111111111111111111111111112", "symbol": "WSOL", "decimals": "9"},
        {"address": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "symbol": "USDC", "decimals": "6"},
        {"address": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB", "symbol": "USDT", "decimals": "6"},
        {"address": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", "symbol": "BONK", "decimals": "5"},
        {"address": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN", "symbol": "JUP", "decimals": "6"},
    ],
}
```

- [ ] **Step 4: Verify models import correctly**

```bash
cd NASE && python -c "from models.types import Token, Pair, PriceQuote, Opportunity; from models.constants import normalize_chain; print('OK')"
```
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
cd NASE && git add -A && git commit -m "feat: data models and chain/token constants"
```

---

### Task 3: Configuration Loader

**Files:**
- Create: `NASE/util/__init__.py`
- Create: `NASE/util/config.py`
- Create: `NASE/config.yaml`
- Create: `NASE/.env`

- [ ] **Step 1: Write util/__init__.py**

```python
from util.config import Config, load_config
from util.rate_limiter import TokenBucket
from util.logging_config import setup_logging

__all__ = ["Config", "load_config", "TokenBucket", "setup_logging"]
```

- [ ] **Step 2: Write util/config.py**

```python
from dataclasses import dataclass, field
from pathlib import Path
import os
import sys

import yaml
from dotenv import load_dotenv


@dataclass
class SourceConfig:
    enabled: bool
    base_url: str
    max_rps: float
    max_concurrent: int
    timeout_seconds: int


@dataclass
class ArbTypes:
    simple: bool = True
    triangular: bool = False
    cross_chain: bool = False


@dataclass
class Filters:
    min_profit_usd: float = 5.00
    max_opportunities: int = 100


@dataclass
class Capital:
    amount_usd: float = 0.0


@dataclass
class Config:
    refresh_interval_seconds: float
    arb_types: ArbTypes
    filters: Filters
    capital: Capital
    chain_gas_estimates: dict[str, float]
    cross_chain_bridge_costs: dict[str, float]
    sources: dict[str, SourceConfig]
    chains: list[str]

    @property
    def enabled_sources(self) -> dict[str, SourceConfig]:
        return {k: v for k, v in self.sources.items() if v.enabled}

    @property
    def enabled_arb_types(self) -> list[str]:
        result = []
        if self.arb_types.simple:
            result.append("simple")
        if self.arb_types.triangular:
            result.append("triangular")
        if self.arb_types.cross_chain:
            result.append("cross_chain")
        return result


def load_config(config_path: str = "config.yaml", env_path: str = ".env") -> Config:
    load_dotenv(dotenv_path=env_path)

    path = Path(config_path)
    if not path.exists():
        print(f"ERROR: Config file not found: {config_path}")
        sys.exit(1)

    with open(path) as f:
        raw = yaml.safe_load(f)

    if raw is None:
        print(f"ERROR: Empty config file: {config_path}")
        sys.exit(1)

    return _parse_config(raw)


def _parse_config(raw: dict) -> Config:
    errors: list[str] = []

    refresh = _get_float(raw, "refresh_interval_seconds", 5.0)
    if refresh <= 0:
        errors.append("refresh_interval_seconds must be positive")

    arb_raw = raw.get("arb_types", {})
    arb_types = ArbTypes(
        simple=arb_raw.get("simple", True),
        triangular=arb_raw.get("triangular", False),
        cross_chain=arb_raw.get("cross_chain", False),
    )
    if not any([arb_types.simple, arb_types.triangular, arb_types.cross_chain]):
        errors.append("At least one arbitrage type must be enabled")

    filters_raw = raw.get("filters", {})
    filters = Filters(
        min_profit_usd=_get_float(filters_raw, "min_profit_usd", 5.0),
        max_opportunities=_get_int(filters_raw, "max_opportunities", 100),
    )

    capital_raw = raw.get("capital", {})
    capital = Capital(amount_usd=_get_float(capital_raw, "amount_usd", 0.0))

    chain_gas = raw.get("chain_gas_estimates", {})
    if not isinstance(chain_gas, dict):
        errors.append("chain_gas_estimates must be a dict")

    bridge = raw.get("cross_chain_bridge_costs", {})
    if not isinstance(bridge, dict):
        errors.append("cross_chain_bridge_costs must be a dict")

    sources_raw = raw.get("sources", {})
    sources: dict[str, SourceConfig] = {}
    enabled_count = 0
    for name, cfg in sources_raw.items():
        if not isinstance(cfg, dict):
            errors.append(f"Source '{name}' must be a dict")
            continue
        sc = SourceConfig(
            enabled=cfg.get("enabled", True),
            base_url=cfg.get("base_url", ""),
            max_rps=_get_float(cfg, "max_rps", 5.0),
            max_concurrent=_get_int(cfg, "max_concurrent", 3),
            timeout_seconds=_get_int(cfg, "timeout_seconds", 30),
        )
        if sc.base_url == "":
            errors.append(f"Source '{name}' missing base_url")
        sources[name] = sc
        if sc.enabled:
            enabled_count += 1

    if enabled_count == 0:
        errors.append("At least one source must be enabled")

    chains = raw.get("chains", [])
    if not isinstance(chains, list) or len(chains) == 0:
        errors.append("chains must be a non-empty list")
    elif not all(isinstance(c, str) for c in chains):
        errors.append("All chain entries must be strings")

    if errors:
        for err in errors:
            print(f"CONFIG ERROR: {err}")
        sys.exit(1)

    return Config(
        refresh_interval_seconds=refresh,
        arb_types=arb_types,
        filters=filters,
        capital=capital,
        chain_gas_estimates=chain_gas,
        cross_chain_bridge_costs=bridge,
        sources=sources,
        chains=chains,
    )


def _get_float(d: dict, key: str, default: float) -> float:
    val = d.get(key, default)
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _get_int(d: dict, key: str, default: int) -> int:
    val = d.get(key, default)
    try:
        return int(val)
    except (TypeError, ValueError):
        return default
```

- [ ] **Step 3: Write config.yaml**

```yaml
refresh_interval_seconds: 5

arb_types:
  simple: true
  triangular: false
  cross_chain: false

filters:
  min_profit_usd: 5.00
  max_opportunities: 100

capital:
  amount_usd: 0.0

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

- [ ] **Step 4: Write .env**

```bash
# NASE API Keys
DEXSCREENER_API_KEY=
DEXPAPRIKA_API_KEY=
SWAPAPI_API_KEY=
NASE_LOG_LEVEL=INFO
```

- [ ] **Step 5: Verify config loads**

```bash
cd NASE && python -c "from util.config import load_config; c = load_config(); print(f'OK: {len(c.sources)} sources, {len(c.chains)} chains, arb_types={c.enabled_arb_types}')"
```
Expected: `OK: 3 sources, 8 chains, arb_types=['simple']`

- [ ] **Step 6: Commit**

```bash
cd NASE && git add -A && git commit -m "feat: configuration loader with validation"
```

---

### Task 4: Rate Limiter (with NASE3 429 retry logic)

**Files:**
- Create: `NASE/util/rate_limiter.py`

- [ ] **Step 1: Write util/rate_limiter.py**

```python
import asyncio
import time


class TokenBucket:
    """Token bucket rate limiter with 429 exponential backoff.

    Pacing: token-bucket algorithm (tokens refill at `rate`/sec, burst capacity).
    429 handling (ported from NASE3): server Retry-After > exponential backoff >
    progressive cooldown after repeated 429s. handle_success() resets backoff.
    """

    _RETRY_DELAYS = [6.0, 12.0, 24.0, 48.0, 60.0]
    _COOLDOWN_REPEATED_429 = 60.0
    _REPEATED_429_THRESHOLD = 3

    def __init__(self, rate: float, burst: int = 1):
        self._rate = max(rate, 0.01)
        self._burst = max(burst, 1)
        self._tokens = float(burst)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

        # 429 backoff state (ported from NASE3 SlidingWindowRateLimiter)
        self._consecutive_429s: int = 0
        self._total_429s: int = 0
        self._total_requests: int = 0
        self._retry_index: int = 0
        self._next_allowed_at: float = 0.0
        self._current_delay: float = 1.0 / rate

    # ---- Token pacing ----

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
        self._last_refill = now

    async def acquire(self) -> None:
        async with self._lock:
            # Cool-down gate (ported from NASE3 acquire())
            now = time.monotonic()
            if now < self._next_allowed_at:
                wait = self._next_allowed_at - now
                await asyncio.sleep(wait)
                now = time.monotonic()

            while self._tokens < 1.0:
                wait = (1.0 - self._tokens) / self._rate
                await asyncio.sleep(wait)
                now = time.monotonic()
                self._refill()
                if self._next_allowed_at > now:
                    extra = self._next_allowed_at - now
                    await asyncio.sleep(extra)
                    now = time.monotonic()

            self._tokens -= 1.0
            self._total_requests += 1

    def available_in(self) -> float:
        """Seconds until next token or cooldown expires (for TUI display)."""
        self._refill()
        pacing_wait = 0.0 if self._tokens >= 1.0 else (1.0 - self._tokens) / self._rate
        now = time.monotonic()
        backoff_wait = max(0.0, self._next_allowed_at - now)
        return max(pacing_wait, backoff_wait)

    # ---- 429 backoff (ported from NASE3) ----

    def handle_429(self, retry_after: float | None = None) -> None:
        """Handle a 429 response. Call when HTTP 429 is received."""
        self._consecutive_429s += 1
        self._total_429s += 1

        if retry_after and retry_after > 0:
            delay = retry_after
        else:
            idx = self._retry_index
            if idx < len(self._RETRY_DELAYS):
                delay = self._RETRY_DELAYS[idx]
                self._retry_index = min(idx + 1, len(self._RETRY_DELAYS) - 1)
            else:
                delay = self._RETRY_DELAYS[-1]

        if self._consecutive_429s > self._REPEATED_429_THRESHOLD:
            delay += self._COOLDOWN_REPEATED_429

        self._next_allowed_at = time.monotonic() + delay
        self._current_delay = max(self._current_delay, delay)

    def handle_success(self) -> None:
        """Reset backoff state after a successful request."""
        if self._consecutive_429s > 0:
            self._consecutive_429s = 0
            self._retry_index = 0
            self._current_delay = 1.0 / self._rate

    # ---- Telemetry (ported from NASE3 get_status()) ----

    @property
    def status(self) -> dict:
        """Rich telemetry for TUI display."""
        now = time.monotonic()
        wait = max(0.0, self._next_allowed_at - now)
        total = self._total_requests + self._total_429s
        return {
            "rate_limited": self._consecutive_429s > 0 and now < self._next_allowed_at,
            "consecutive_429s": self._consecutive_429s,
            "total_429s": self._total_429s,
            "time_until_next": wait,
            "current_delay": self._current_delay,
            "total_requests": self._total_requests,
            "success_rate": round((self._total_requests / total * 100) if total > 0 else 100.0, 1),
        }

    @property
    def rate(self) -> float:
        return self._rate
```

- [ ] **Step 2: Verify rate limiter works (pacing + 429 backoff)**

```bash
cd NASE && python3 -c "
import asyncio, time
from util.rate_limiter import TokenBucket
async def test():
    bucket = TokenBucket(rate=10, burst=5)
    t0 = time.monotonic()
    for _ in range(10):
        await bucket.acquire()
    dt = time.monotonic() - t0
    print(f'Pacing OK: 10 acquires in {dt:.2f}s (rate=10, burst=5)')
    # Test 429 backoff
    bucket.handle_429(retry_after=3.0)
    print(f'429 status: {bucket.status}')
    assert bucket.status['rate_limited'] == True
    assert bucket.status['consecutive_429s'] == 1
    bucket.handle_success()
    print(f'After success: consecutive_429s={bucket.status["consecutive_429s"]}')
    assert bucket.status['consecutive_429s'] == 0
    print('429 backoff OK')
asyncio.run(test())
"
```
Expected: `Pacing OK: 10 acquires in ~0.5s` then `429 status: ...` then `429 backoff OK`

- [ ] **Step 3: Verify repeated 429 escalates cooldown**

```bash
cd NASE && python3 -c "
import asyncio
from util.rate_limiter import TokenBucket
async def test():
    b = TokenBucket(rate=5, burst=2)
    for i in range(5):
        b.handle_429()
        s = b.status
        print(f'429 #{i+1}: delay={s["current_delay"]:.0f}s, consecutive={s["consecutive_429s"]}')
    # After 4th 429 (threshold=3), extra 60s cooldown kicks in
    assert b.status['current_delay'] >= 120.0
    print('Escalation OK')
asyncio.run(test())
"
```
Expected: delays escalate through [6, 12, 24, 48, 60] then 60+60=120 at 5th

- [ ] **Step 4: Commit**

```bash
cd NASE && git add -A && git commit -m "feat: token bucket rate limiter with NASE3 429 exponential backoff"
```

---

### Task 5: Logging Setup

**Files:**
- Create: `NASE/util/logging_config.py`

- [ ] **Step 1: Write util/logging_config.py**

```python
import logging
import json
import os
import sys
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "event": record.getMessage(),
        }
        if hasattr(record, "source"):
            payload["source"] = record.source
        for key in ("duration_ms", "pairs", "opportunities", "status", "url"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        return json.dumps(payload, default=str)


def setup_logging(log_file: str = "nase.log") -> logging.Logger:
    logger = logging.getLogger("nase")
    logger.setLevel(os.getenv("NASE_LOG_LEVEL", "INFO"))
    logger.handlers.clear()

    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(JSONFormatter())
    file_handler.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.WARNING)
    console_fmt = logging.Formatter("NASE [%(levelname)s] %(message)s")
    console_handler.setFormatter(console_fmt)
    logger.addHandler(console_handler)

    return logger
```

- [ ] **Step 2: Verify logging works**

```bash
cd NASE && python -c "
from util.logging_config import setup_logging
logger = setup_logging(log_file='/tmp/nase-test.log')
logger.info('test', extra={'pairs': 42})
import json
with open('/tmp/nase-test.log') as f:
    rec = json.loads(f.readline())
    assert rec['event'] == 'test'
    assert rec['pairs'] == 42
    assert rec['level'] == 'INFO'
print('OK')
rm -f /tmp/nase-test.log
"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd NASE && git add -A && git commit -m "feat: structured JSON-line logging"
```

---

### Task 6: Source Base Class (with 429 bucket integration)

**Files:**
- Create: `NASE/sources/__init__.py`
- Create: `NASE/sources/base.py`

- [ ] **Step 1: Write sources/__init__.py**

```python
from sources.base import Source
from sources.dexscreener import DexScreenerSource
from sources.dexpaprika import DexPaprikaSource
from sources.swapapi import SwapApiSource

__all__ = ["Source", "DexScreenerSource", "DexPaprikaSource", "SwapApiSource"]
```

- [ ] **Step 2: Write sources/base.py**

```python
from abc import ABC, abstractmethod
import asyncio
import logging
from typing import Optional

import aiohttp

from models.types import PriceQuote
from util.config import SourceConfig
from util.rate_limiter import TokenBucket

logger = logging.getLogger("nase")


class Source(ABC):
    name: str

    def __init__(self, config: SourceConfig, api_key: Optional[str] = None):
        self.config = config
        self.api_key = api_key
        self._bucket = TokenBucket(rate=config.max_rps, burst=config.max_concurrent)
        self._semaphore = asyncio.Semaphore(config.max_concurrent)
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def healthy(self) -> bool:
        return not self._bucket.status["rate_limited"]

    @property
    def bucket_status(self) -> dict:
        """Full telemetry from the rate limiter (for TUI display)."""
        return self._bucket.status

    async def start(self) -> None:
        connector = aiohttp.TCPConnector(
            limit=self.config.max_concurrent,
            enable_cleanup_closed=True,
            ttl_dns_cache=300,
            force_close=False,
        )
        timeout = aiohttp.ClientTimeout(total=self.config.timeout_seconds)
        self._session = aiohttp.ClientSession(connector=connector, timeout=timeout)

    async def stop(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    async def fetch(self) -> list[PriceQuote]:
        if not self._session:
            raise RuntimeError(f"Source {self.name} not started")

        # Check bucket backoff state (ported from NASE3 cooldown gate)
        if self._bucket.status["rate_limited"]:
            wait = self._bucket.status["time_until_next"]
            logger.warning(
                "Source %s in backoff %.1fs (429#%d)",
                self.name, wait, self._bucket.status["consecutive_429s"],
                extra={"source": self.name},
            )
            return []

        try:
            results = await self._fetch_impl()
            logger.info(
                "Source %s fetched %d pairs",
                self.name,
                len(results),
                extra={"source": self.name, "pairs": len(results)},
            )
            return results
        except RateLimitedError:
            logger.warning(
                "Source %s 429 backoff %.0fs",
                self.name,
                self._bucket.status["current_delay"],
                extra={"source": self.name},
            )
            return []
        except Exception as e:
            logger.error(
                "Source %s failed: %s",
                self.name,
                str(e),
                extra={"source": self.name},
            )
            return []

    async def _get(self, url: str, **kwargs) -> dict:
        """HTTP GET with bucket pacing and 429 backoff integration."""
        await self._bucket.acquire()
        async with self._semaphore:
            async with self._session.get(url, **kwargs) as resp:
                if resp.status == 429:
                    retry = self._parse_retry_after(resp.headers)
                    self._bucket.handle_429(retry)
                    logger.warning(
                        "Source %s 429: retry-after=%s, backoff=%.0fs (429#%d)",
                        self.name, retry, self._bucket.status["current_delay"],
                        self._bucket.status["consecutive_429s"],
                        extra={"source": self.name, "status": 429},
                    )
                    raise RateLimitedError("Rate limited")
                resp.raise_for_status()
                self._bucket.handle_success()
                return await resp.json()

    async def _post(self, url: str, json_data: dict, **kwargs) -> dict:
        """HTTP POST with bucket pacing and 429 backoff integration."""
        await self._bucket.acquire()
        async with self._semaphore:
            async with self._session.post(url, json=json_data, **kwargs) as resp:
                if resp.status == 429:
                    retry = self._parse_retry_after(resp.headers)
                    self._bucket.handle_429(retry)
                    logger.warning(
                        "Source %s 429: retry-after=%s, backoff=%.0fs (429#%d)",
                        self.name, retry, self._bucket.status["current_delay"],
                        self._bucket.status["consecutive_429s"],
                        extra={"source": self.name, "status": 429},
                    )
                    raise RateLimitedError("Rate limited")
                resp.raise_for_status()
                self._bucket.handle_success()
                return await resp.json()

    @staticmethod
    def _parse_retry_after(headers) -> float | None:
        """Extract Retry-After header as seconds (NASE3 pattern)."""
        val = headers.get("Retry-After") or headers.get("retry-after")
        if val is None:
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    @abstractmethod
    async def _fetch_impl(self) -> list[PriceQuote]:
        ...


class RateLimitedError(Exception):
    pass
```

- [ ] **Step 3: Verify base class imports**

```bash
cd NASE && python3 -c "
from sources.base import Source, RateLimitedError
print('OK')
"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
cd NASE && git add -A && git commit -m "feat: source base class with 429 retry integration and bucket status reporting"
```

---

### Task 7: DexScreener Source

**Files:**
- Create: `NASE/sources/dexscreener.py`

- [ ] **Step 1: Write sources/dexscreener.py**

```python
import asyncio
import logging
import time
from decimal import Decimal, DecimalException
from typing import Optional

from sources.base import Source
from models.types import Token, Pair, PriceQuote
from models.constants import normalize_chain, KNOWN_TOKENS
from util.config import SourceConfig

logger = logging.getLogger("nase")


class DexScreenerSource(Source):
    name = "dexscreener"

    def __init__(self, config: SourceConfig, api_key: Optional[str] = None):
        super().__init__(config, api_key)
        self._seen_pairs: set[str] = set()
        self._token_cache: dict[str, list[Token]] = {}

    async def _fetch_impl(self) -> list[PriceQuote]:
        quotes: list[PriceQuote] = []
        known = self._get_tokens_to_search()
        searches = [self._search_token(symbol) for symbol in known]
        results = await asyncio.gather(*searches, return_exceptions=True)
        for result in results:
            if isinstance(result, list):
                quotes.extend(result)
            elif isinstance(result, Exception):
                logger.warning("%s token search failed: %s", self.name, str(result))
        return quotes

    def _get_tokens_to_search(self) -> list[tuple[str, str]]:
        pairs = []
        for chain, tokens in KNOWN_TOKENS.items():
            for t in tokens:
                pairs.append((t["symbol"], chain))
        return pairs

    async def _search_token(self, info: tuple[str, str]) -> list[PriceQuote]:
        symbol, chain = info
        url = f"{self.config.base_url}/latest/dex/search?q={symbol}"
        try:
            data = await self._get(url)
        except Exception:
            return []
        return self._normalize(data, chain)

    def _normalize(self, raw: dict, chain: str) -> list[PriceQuote]:
        quotes: list[PriceQuote] = []
        pairs = raw.get("pairs", [])
        if not isinstance(pairs, list):
            return quotes
        now = time.time()
        for p in pairs:
            try:
                pair_addr = p.get("pairAddress", "")
                if pair_addr in self._seen_pairs:
                    continue
                self._seen_pairs.add(pair_addr)

                base_tok = p.get("baseToken", {})
                quote_tok = p.get("quoteToken", {})

                base = Token(
                    address=base_tok.get("address", ""),
                    symbol=base_tok.get("symbol", "???"),
                    chain=normalize_chain(p.get("chainId", chain)),
                    decimals=0,
                )
                quote = Token(
                    address=quote_tok.get("address", ""),
                    symbol=quote_tok.get("symbol", "???"),
                    chain=normalize_chain(p.get("chainId", chain)),
                    decimals=0,
                )
                pair = Pair(base=base, quote=quote, pair_address=pair_addr)

                price_str = p.get("priceUsd", "0")
                if not price_str or price_str in ("", "0", "0.0"):
                    continue
                price = Decimal(str(price_str))
                price_change = Decimal(str(p.get("priceChange", {}).get("h24", 0)))
                spread_estimate = abs(price_change) * price / Decimal("100")
                ask = price
                bid = price + spread_estimate

                quote_obj = PriceQuote(
                    pair=pair,
                    dex=p.get("dexId", "unknown"),
                    source_api="dexscreener",
                    ask_price=ask,
                    bid_price=bid,
                    liquidity_usd=float(p.get("liquidity", {}).get("usd", 0) or 0),
                    volume_24h_usd=float(p.get("volume", {}).get("h24", 0) or 0),
                    fetched_at=now,
                )
                quotes.append(quote_obj)
            except (KeyError, TypeError, DecimalException):
                continue
        return quotes
```

- [ ] **Step 2: Commit**

```bash
cd NASE && git add -A && git commit -m "feat: DexScreener source with token-based pair discovery"
```

---

### Task 8: DexPaprika Source

**Files:**
- Create: `NASE/sources/dexpaprika.py`

- [ ] **Step 1: Write sources/dexpaprika.py**

```python
import asyncio
import logging
import time
from decimal import Decimal, DecimalException
from typing import Optional

from sources.base import Source
from models.types import Token, Pair, PriceQuote
from models.constants import normalize_chain
from util.config import SourceConfig

logger = logging.getLogger("nase")


class DexPaprikaSource(Source):
    name = "dexpaprika"

    def __init__(self, config: SourceConfig, api_key: Optional[str] = None):
        super().__init__(config, api_key)
        self._seen_pairs: set[str] = set()

    async def _fetch_impl(self) -> list[PriceQuote]:
        quotes: list[PriceQuote] = []
        self._seen_pairs.clear()
        return quotes

    async def _fetch_pools_page(self, chain: str, page: int = 0, limit: int = 100) -> list[PriceQuote]:
        url = f"{self.config.base_url}/networks/{chain}/pools"
        params = {"page": page, "limit": limit}
        try:
            data = await self._get(url, params=params)
        except Exception:
            return []
        return self._normalize_pools(data.get("pools", []), chain)

    def _normalize_pools(self, pools: list[dict], chain: str) -> list[PriceQuote]:
        return []
```

- [ ] **Step 2: Commit**

```bash
cd NASE && git add -A && git commit -m "feat: DexPaprika source skeleton"
```

---

### Task 9: SwapAPI Source

**Files:**
- Create: `NASE/sources/swapapi.py`

- [ ] **Step 1: Write sources/swapapi.py**

```python
import logging
import time
from decimal import Decimal, DecimalException
from typing import Optional

from sources.base import Source
from models.types import Token, Pair, PriceQuote
from models.constants import normalize_chain, KNOWN_TOKENS
from util.config import SourceConfig

logger = logging.getLogger("nase")


class SwapApiSource(Source):
    name = "swapapi"

    def __init__(self, config: SourceConfig, api_key: Optional[str] = None):
        super().__init__(config, api_key)

    async def _fetch_impl(self) -> list[PriceQuote]:
        if not self.api_key:
            logger.warning("SwapAPI: no API key configured, skipping")
            return []

        quotes: list[PriceQuote] = []
        return quotes

    def _normalize_price(self, token_info: dict, chain: str) -> list[PriceQuote]:
        return []
```

- [ ] **Step 2: Commit**

```bash
cd NASE && git add -A && git commit -m "feat: SwapAPI source skeleton"
```

---

### Task 10: Pipeline Collector

**Files:**
- Create: `NASE/pipeline/__init__.py`
- Create: `NASE/pipeline/collector.py`

- [ ] **Step 1: Write pipeline/__init__.py**

```python
from pipeline.collector import Collector
from pipeline.normalizer import Normalizer
from pipeline.matcher import Matcher
from pipeline.scanner import Scanner
from pipeline.filter import ResultFilter

__all__ = ["Collector", "Normalizer", "Matcher", "Scanner", "ResultFilter"]
```

- [ ] **Step 2: Write pipeline/collector.py**

```python
import asyncio
import logging
import time

from sources.base import Source
from models.types import PriceQuote
from util.config import Config

logger = logging.getLogger("nase")


class Collector:
    def __init__(self, config: Config):
        self.config = config
        self._sources: list[Source] = []

    def register(self, source: Source) -> None:
        self._sources.append(source)

    @property
    def source_statuses(self) -> dict[str, dict]:
        statuses = {}
        for src in self._sources:
            bs = src.bucket_status
            statuses[src.name] = {
                "healthy": src.healthy,
                "rate_limited": bs["rate_limited"],
                "rate_wait_seconds": bs["time_until_next"],
                "consecutive_429s": bs["consecutive_429s"],
                "total_429s": bs["total_429s"],
                "success_rate": bs["success_rate"],
            }
        return statuses

    async def start_all(self) -> None:
        tasks = [src.start() for src in self._sources]
        await asyncio.gather(*tasks)

    async def stop_all(self) -> None:
        tasks = [src.stop() for src in self._sources]
        await asyncio.gather(*tasks)

    async def collect(self) -> dict[str, list[PriceQuote]]:
        tasks = [src.fetch() for src in self._sources]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        output: dict[str, list[PriceQuote]] = {}
        for source, result in zip(self._sources, results):
            if isinstance(result, Exception):
                logger.error("%s: %s", source.name, str(result))
                output[source.name] = []
            else:
                output[source.name] = result
        return output
```

- [ ] **Step 3: Commit**

```bash
cd NASE && git add -A && git commit -m "feat: pipeline collector with concurrent source orchestration"
```

---

### Task 11: Pipeline Normalizer

**Files:**
- Create: `NASE/pipeline/normalizer.py`

- [ ] **Step 1: Write pipeline/normalizer.py**

```python
import logging
import time

from models.types import PriceQuote
from util.config import Config

logger = logging.getLogger("nase")


class Normalizer:
    def __init__(self, config: Config):
        self.config = config
        self._max_age = config.refresh_interval_seconds * 2

    def normalize_all(self, raw_data: dict[str, list[PriceQuote]]) -> list[PriceQuote]:
        all_quotes: list[PriceQuote] = []
        now = time.time()

        for source_name, quotes in raw_data.items():
            for q in quotes:
                if q.ask_price <= 0 or q.bid_price <= 0:
                    continue
                if q.ask_price < 0 or q.bid_price < 0:
                    continue
                if now - q.fetched_at > self._max_age:
                    continue
                if not self._is_valid_address(q.pair.base.address):
                    continue
                if not self._is_valid_address(q.pair.quote.address):
                    continue
                all_quotes.append(q)

        logger.info("Normalized %d total quotes from %d sources", len(all_quotes), len(raw_data))
        return all_quotes

    @staticmethod
    def _is_valid_address(addr: str) -> bool:
        if not addr or len(addr) < 10:
            return False
        return addr.startswith("0x") or addr.isalnum()
```

- [ ] **Step 2: Commit**

```bash
cd NASE && git add -A && git commit -m "feat: pipeline normalizer with validation and age filtering"
```

---

### Task 12: Pipeline Matcher

**Files:**
- Create: `NASE/pipeline/matcher.py`

- [ ] **Step 1: Write pipeline/matcher.py**

```python
import logging
from collections import defaultdict

from models.types import PriceQuote

logger = logging.getLogger("nase")


class MatchedGroup:
    def __init__(self, chain: str, base_address: str, quote_address: str):
        self.chain = chain
        self.base_address = base_address
        self.quote_address = quote_address
        self.quotes: list[PriceQuote] = []

    @property
    def is_actionable(self) -> bool:
        dexs = {q.dex for q in self.quotes}
        return len(dexs) >= 2


class Matcher:
    def match(self, quotes: list[PriceQuote], enabled_arb_types: list[str]) -> list[MatchedGroup]:
        groups: dict[tuple[str, str, str], MatchedGroup] = {}

        for q in quotes:
            key = (q.pair.chain, q.pair.base.address.lower(), q.pair.quote.address.lower())
            if key not in groups:
                groups[key] = MatchedGroup(
                    chain=q.pair.chain,
                    base_address=q.pair.base.address,
                    quote_address=q.pair.quote.address,
                )
            groups[key].quotes.append(q)

        actionable = [g for g in groups.values() if g.is_actionable]
        logger.info("Matched %d groups, %d actionable (>=2 DEXes)", len(groups), len(actionable))
        return actionable
```

- [ ] **Step 2: Commit**

```bash
cd NASE && git add -A && git commit -m "feat: pipeline matcher grouping quotes by chain and pair"
```

---

### Task 13: Pipeline Scanner

**Files:**
- Create: `NASE/pipeline/scanner.py`

- [ ] **Step 1: Write pipeline/scanner.py**

```python
import logging
import time
from decimal import Decimal

from models.types import PriceQuote, Pair, Opportunity
from pipeline.matcher import MatchedGroup
from util.config import Config

logger = logging.getLogger("nase")


class Scanner:
    def __init__(self, config: Config):
        self.config = config
        self._gas_estimates = config.chain_gas_estimates
        self._bridge_costs = config.cross_chain_bridge_costs

    def scan(self, groups: list[MatchedGroup], enabled_arb_types: list[str]) -> list[Opportunity]:
        opportunities: list[Opportunity] = []

        if "simple" in enabled_arb_types:
            for group in groups:
                opp = self._scan_simple(group)
                if opp:
                    opportunities.append(opp)

        if "triangular" in enabled_arb_types:
            tri = self._scan_triangular(groups)
            opportunities.extend(tri)

        if "cross_chain" in enabled_arb_types:
            cross = self._scan_cross_chain(groups)
            opportunities.extend(cross)

        logger.info("Scanned: %d opportunities found", len(opportunities))
        return opportunities

    def _scan_simple(self, group: MatchedGroup) -> Opportunity | None:
        if not group.quotes:
            return None
        buy = min(group.quotes, key=lambda q: q.ask_price)
        sell = max(group.quotes, key=lambda q: q.bid_price)
        if buy is None or sell is None:
            return None
        if buy.dex == sell.dex:
            return None
        if buy.ask_price <= 0 or sell.bid_price <= 0:
            return None

        spread_pct = float(
            ((sell.bid_price - buy.ask_price) / buy.ask_price) * Decimal("100")
        )
        if spread_pct <= 0:
            return None

        gas = self._gas_estimates.get(group.chain, 5.0)
        net = (spread_pct / 100.0) * self.config.capital.amount_usd - gas if self.config.capital.amount_usd > 0 else 0.0

        sources = sorted(set(q.source_api for q in group.quotes))
        return Opportunity(
            pair=buy.pair,
            buy_at_dex=buy.dex,
            sell_at_dex=sell.dex,
            buy_price=buy.ask_price,
            sell_price=sell.bid_price,
            spread_pct=round(spread_pct, 4),
            net_profit_usd=round(net, 2),
            source_apis=sources,
            detected_at=time.time(),
        )

    def _scan_triangular(self, groups: list[MatchedGroup]) -> list[Opportunity]:
        return []

    def _scan_cross_chain(self, groups: list[MatchedGroup]) -> list[Opportunity]:
        return []
```

- [ ] **Step 2: Commit**

```bash
cd NASE && git add -A && git commit -m "feat: pipeline scanner with simple cross-DEX arb detection"
```

---

### Task 14: Pipeline Filter

**Files:**
- Create: `NASE/pipeline/filter.py`

- [ ] **Step 1: Write pipeline/filter.py**

```python
import logging

from models.types import Opportunity
from util.config import Config

logger = logging.getLogger("nase")


class ResultFilter:
    def __init__(self, config: Config):
        self.config = config

    def apply(self, opportunities: list[Opportunity]) -> list[Opportunity]:
        if not opportunities:
            return []

        if self.config.capital.amount_usd > 0:
            opps = self._recalculate_for_capital(opportunities)
        else:
            opps = list(opportunities)

        opps = self._filter_by_profit(opps)
        opps = self._deduplicate(opps)
        opps.sort(key=lambda o: o.spread_pct if self.config.capital.amount_usd == 0 else o.net_profit_usd, reverse=True)
        opps = opps[:self.config.filters.max_opportunities]

        logger.info("Filter: %d opportunities after filtering", len(opps))
        return opps

    def _recalculate_for_capital(self, opportunities: list[Opportunity]) -> list[Opportunity]:
        capital = self.config.capital.amount_usd
        result = []
        for o in opportunities:
            gas = self.config.chain_gas_estimates.get(o.pair.chain, 5.0)
            net = (o.spread_pct / 100.0) * capital - gas
            result.append(Opportunity(
                pair=o.pair,
                buy_at_dex=o.buy_at_dex,
                sell_at_dex=o.sell_at_dex,
                buy_price=o.buy_price,
                sell_price=o.sell_price,
                spread_pct=o.spread_pct,
                net_profit_usd=round(net, 2),
                source_apis=o.source_apis,
                detected_at=o.detected_at,
            ))
        return result

    def _filter_by_profit(self, opportunities: list[Opportunity]) -> list[Opportunity]:
        threshold = self.config.filters.min_profit_usd
        if self.config.capital.amount_usd > 0:
            return [o for o in opportunities if o.net_profit_usd >= threshold]
        return opportunities

    def _deduplicate(self, opportunities: list[Opportunity]) -> list[Opportunity]:
        seen: dict[tuple, Opportunity] = {}
        for o in opportunities:
            key = (o.pair.pair_address.lower(), o.buy_at_dex, o.sell_at_dex)
            if key in seen:
                existing = seen[key]
                combined = list(set(existing.source_apis + o.source_apis))
                if o.spread_pct < existing.spread_pct:
                    seen[key] = Opportunity(
                        pair=o.pair,
                        buy_at_dex=o.buy_at_dex,
                        sell_at_dex=o.sell_at_dex,
                        buy_price=o.buy_price,
                        sell_price=o.sell_price,
                        spread_pct=o.spread_pct,
                        net_profit_usd=o.net_profit_usd,
                        source_apis=combined,
                        detected_at=min(o.detected_at, existing.detected_at),
                    )
                else:
                    seen[key] = existing
                    seen[key].source_apis = combined
            else:
                seen[key] = o
        return list(seen.values())
```

- [ ] **Step 2: Commit**

```bash
cd NASE && git add -A && git commit -m "feat: pipeline filter with profit threshold, dedup, and sort"
```

---

### Task 15: TUI Status Bar Widget

**Files:**
- Create: `NASE/tui/__init__.py`
- Create: `NASE/tui/status.py`

- [ ] **Step 1: Write tui/__init__.py**

```python
from tui.app import NaseApp

__all__ = ["NaseApp"]
```

- [ ] **Step 2: Write tui/status.py**

```python
from textual.widgets import Static


class StatusBar(Static):
    DEFAULT_CSS = """
    StatusBar {
        height: auto;
        padding: 0 1;
        color: $text-muted;
    }
    StatusBar .green { color: #22c55e; }
    StatusBar .red { color: #ef4444; }
    StatusBar .yellow { color: #eab308; }
    """

    def render(self) -> str:
        sources_text = self._render_sources()
        chains_text = self._render_chains()
        return f"SOURCES: {sources_text}\nCHAINS: {chains_text}"

    def _render_sources(self) -> str:
        statuses = self.app._pipeline_data.get("statuses", {})
        parts = []
        for name, info in statuses.items():
            if info["healthy"]:
                c429 = info.get("consecutive_429s", 0)
                if c429 > 0:
                    mark = f"[yellow]✓ {c429}x429[/]"
                else:
                    sr = info.get("success_rate", 100)
                    mark = f"[green]✓ {sr:.0f}%[/]"
            elif info.get("rate_limited"):
                wait = info.get("rate_wait_seconds", 0)
                c429 = info.get("consecutive_429s", 0)
                mark = f"[yellow]⏳ {wait:.0f}s ({c429}x429)[/]"
            else:
                mark = "[red]✗[/]"
            parts.append(f"{name} {mark}")
        return "  ".join(parts) if parts else "No sources"

    def _render_chains(self) -> str:
        chain_counts = self.app._pipeline_data.get("chain_counts", {})
        if not chain_counts:
            return "No data"
        parts = [f"{chain}({count})" for chain, count in chain_counts.items()]
        return " ".join(parts)
```

- [ ] **Step 3: Commit**

```bash
cd NASE && git add -A && git commit -m "feat: TUI status bar with source health and chain counts"
```

---

### Task 16: TUI Header & Controls Widgets

**Files:**
- Create: `NASE/tui/header.py`
- Create: `NASE/tui/controls.py`

- [ ] **Step 1: Write tui/header.py**

```python
from textual.widgets import Static


class HeaderBar(Static):
    DEFAULT_CSS = """
    HeaderBar {
        height: 1;
        background: $panel;
        color: $text;
        padding: 0 1;
    }
    """

    def render(self) -> str:
        cycle = self.app._pipeline_data.get("cycle_time", 0)
        pairs = self.app._pipeline_data.get("total_pairs", 0)
        opps = self.app._pipeline_data.get("opportunity_count", 0)
        return (
            f"NASE v0.1    Cycle: {cycle:.1f}s    "
            f"Pairs: {pairs:,}    Opportunities: {opps}    "
            f"[dim][q] quit[/]"
        )
```

- [ ] **Step 2: Write tui/controls.py**

```python
from textual.widgets import Static


class ControlsBar(Static):
    DEFAULT_CSS = """
    ControlsBar {
        height: 1;
        color: $text-muted;
        padding: 0 1;
        background: $panel-lighten-1;
    }
    """

    def render(self) -> str:
        arb = self.app._pipeline_data.get("active_arb_types", ["simple"])
        arb_simple = "[[bold]SIMPLE[/]]" if "simple" in arb else "[dim]SIMPLE[/]"
        arb_tri = "[[bold]TRI[/]]" if "triangular" in arb else "[dim]TRI[/]"
        arb_cross = "[[bold]CROSS[/]]" if "cross_chain" in arb else "[dim]CROSS[/]"
        capital = self.app._pipeline_data.get("capital", 0)
        cap_text = f"[bold]${capital:,.0f}[/]" if capital > 0 else "[dim]$0[/]"
        min_profit = self.app._pipeline_data.get("min_profit", 5.0)
        return (
            f"ARB: {arb_simple} {arb_tri} {arb_cross}    "
            f"CAPITAL: {cap_text}    "
            f"MIN PROFIT: [bold]${min_profit:,.2f}[/]    "
            f"[dim][s] sort  [a] toggle arb  [c] capital  [+/-] threshold[/]"
        )
```

- [ ] **Step 3: Commit**

```bash
cd NASE && git add -A && git commit -m "feat: TUI header and controls bar widgets"
```

---

### Task 17: TUI Table & Detail Widgets

**Files:**
- Create: `NASE/tui/table.py`
- Create: `NASE/tui/detail.py`

- [ ] **Step 1: Write tui/table.py**

```python
from textual.widgets import DataTable

from models.types import Opportunity


class OpportunityTable(DataTable):
    DEFAULT_CSS = """
    OpportunityTable {
        height: 1fr;
    }
    """

    def on_mount(self) -> None:
        self.cursor_type = "row"
        self.add_columns("#", "Pair", "Buy At", "Sell At", "Spread", "Profit", "Age", "Ch")

    def update_data(self, opportunities: list[Opportunity], use_capital: bool) -> None:
        self.clear()
        for i, o in enumerate(opportunities, 1):
            age = f"{o.age_seconds:.0f}s"
            chain_short = o.pair.chain[:2].upper()
            if use_capital and o.net_profit_usd > 0:
                profit = f"${o.net_profit_usd:,.2f}"
            elif not use_capital:
                profit = f"({o.spread_pct:.2f}%)"
            else:
                profit = f"${o.net_profit_usd:,.2f}"

            spread_color = self._spread_style(o.spread_pct, o.age_seconds)
            self.add_row(
                str(i),
                f"{o.pair.base.symbol}/{o.pair.quote.symbol}",
                o.buy_at_dex,
                o.sell_at_dex,
                spread_color,
                profit,
                age,
                chain_short,
                key=o.pair.pair_address,
            )

    @staticmethod
    def _spread_style(spread_pct: float, age: float) -> str:
        if age > 15:
            color = "#ef4444"
        elif spread_pct >= 2.0:
            color = "#22c55e"
        elif spread_pct >= 1.0:
            color = "#eab308"
        else:
            return f"{spread_pct:.2f}%"
        return f"[{color}]{spread_pct:.2f}%[/]"
```

- [ ] **Step 2: Write tui/detail.py**

```python
from textual.containers import Vertical
from textual.widgets import Static

from models.types import PriceQuote


class DetailPanel(Vertical):
    DEFAULT_CSS = """
    DetailPanel {
        height: auto;
        max-height: 12;
        border: solid $accent;
        padding: 0 1;
        background: $panel;
        display: none;
    }
    DetailPanel.visible {
        display: block;
    }
    """

    def show_opportunity(self, opp, source_quotes: list[PriceQuote], capital: float) -> None:
        self.remove_class("hidden")
        self.add_class("visible")
        lines = [f"[bold]Details: {opp.pair.base.symbol}/{opp.pair.quote.symbol} on {opp.pair.chain}[/]"]
        volume = 0.0
        liquidity = 0.0
        for q in source_quotes:
            if q.dex == opp.buy_at_dex:
                volume = q.volume_24h_usd
                liquidity = q.liquidity_usd
        lines.append(
            f"  [bold]Buy at:[/] {opp.buy_at_dex}    ASK: ${opp.buy_price:,.2f}    "
            f"24h Vol: ${volume:,.0f}    Liq: ${liquidity:,.0f}"
        )
        volume2 = 0.0
        liq2 = 0.0
        for q in source_quotes:
            if q.dex == opp.sell_at_dex:
                volume2 = q.volume_24h_usd
                liq2 = q.liquidity_usd
        lines.append(
            f"  [bold]Sell at:[/] {opp.sell_at_dex}   BID: ${opp.sell_price:,.2f}    "
            f"24h Vol: ${volume2:,.0f}    Liq: ${liq2:,.0f}"
        )
        gross = opp.sell_price - opp.buy_price
        gas = 8.0
        net = opp.net_profit_usd
        lines.append(f"  Spread: {opp.spread_pct:.2f}%    Gross: ${gross:,.2f}    Net: ${net:,.2f}")
        if capital > 0:
            out = capital * (1 + opp.spread_pct / 100)
            lines.append(f"  Capital ${capital:,.0f} -> Output: ${out:,.2f}")
        src_badge = " ".join(f"[{s[:2]}]" for s in sorted(opp.source_apis))
        lines.append(f"  Sources: {src_badge}")
        self.mount(Static("\n".join(lines)))

    def hide_panel(self) -> None:
        self.remove_class("visible")
        self.add_class("hidden")
        self.query(Static).remove()
```

- [ ] **Step 3: Commit**

```bash
cd NASE && git add -A && git commit -m "feat: TUI opportunity table and detail panel widgets"
```

---

### Task 18: TUI Application

**Files:**
- Create: `NASE/tui/app.py`

- [ ] **Step 1: Write tui/app.py**

```python
import asyncio
import time
from collections import defaultdict

from textual.app import App, ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Footer

from tui.header import HeaderBar
from tui.controls import ControlsBar
from tui.table import OpportunityTable
from tui.detail import DetailPanel
from tui.status import StatusBar

from pipeline.collector import Collector
from pipeline.normalizer import Normalizer
from pipeline.matcher import Matcher
from pipeline.scanner import Scanner
from pipeline.filter import ResultFilter

from sources.dexscreener import DexScreenerSource
from sources.dexpaprika import DexPaprikaSource
from sources.swapapi import SwapApiSource

from util.config import Config

import logging
logger = logging.getLogger("nase")


class NaseApp(App):
    CSS = """
    Screen {
        layout: vertical;
    }
    #header { dock: top; }
    #controls { dock: top; }
    #main-table { height: 1fr; }
    #detail { dock: bottom; }
    #status { dock: bottom; }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("a", "toggle_arb", "Toggle Arb Type"),
        ("s", "change_sort", "Change Sort"),
        ("c", "set_capital", "Set Capital"),
        ("r", "force_refresh", "Force Refresh"),
        ("h", "toggle_help", "Help"),
        ("plus", "increase_threshold", "Increase Threshold"),
        ("minus", "decrease_threshold", "Decrease Threshold"),
    ]

    def __init__(self, config: Config):
        super().__init__()
        self._config = config
        self._collector = Collector(config)
        self._normalizer = Normalizer(config)
        self._matcher = Matcher()
        self._scanner = Scanner(config)
        self._filter = ResultFilter(config)
        self._pipeline_data: dict = {
            "cycle_time": 0,
            "total_pairs": 0,
            "opportunity_count": 0,
            "statuses": {},
            "chain_counts": {},
            "active_arb_types": config.enabled_arb_types,
            "capital": config.capital.amount_usd,
            "min_profit": config.filters.min_profit_usd,
            "sort_column": "profit",
        }
        self._opportunities: list = []
        self._all_quotes: list = []
        self._cycle_task: asyncio.Task | None = None

    @property
    def pipeline_data(self) -> dict:
        return self._pipeline_data

    def compose(self) -> ComposeResult:
        yield HeaderBar(id="header")
        yield ControlsBar(id="controls")
        yield OpportunityTable(id="main-table")
        yield DetailPanel(id="detail")
        yield StatusBar(id="status")

    async def on_mount(self) -> None:
        self._setup_sources()
        await self._collector.start_all()
        self._cycle_task = asyncio.create_task(self._run_cycles())

    async def on_unmount(self) -> None:
        if self._cycle_task:
            self._cycle_task.cancel()
        await self._collector.stop_all()

    def _setup_sources(self) -> None:
        import os
        if self._config.sources.get("dexscreener") and self._config.sources["dexscreener"].enabled:
            self._collector.register(DexScreenerSource(
                self._config.sources["dexscreener"],
                os.getenv("DEXSCREENER_API_KEY"),
            ))
        if self._config.sources.get("dexpaprika") and self._config.sources["dexpaprika"].enabled:
            self._collector.register(DexPaprikaSource(
                self._config.sources["dexpaprika"],
                os.getenv("DEXPAPRIKA_API_KEY"),
            ))
        if self._config.sources.get("swapapi") and self._config.sources["swapapi"].enabled:
            self._collector.register(SwapApiSource(
                self._config.sources["swapapi"],
                os.getenv("SWAPAPI_API_KEY"),
            ))

    async def _run_cycles(self) -> None:
        while True:
            cycle_start = time.monotonic()
            await self._run_single_cycle()
            elapsed = time.monotonic() - cycle_start
            self._pipeline_data["cycle_time"] = elapsed
            sleep_for = max(0, self._config.refresh_interval_seconds - elapsed)
            await asyncio.sleep(sleep_for)

    async def _run_single_cycle(self) -> None:
        raw = await self._collector.collect()
        self._all_quotes = self._normalizer.normalize_all(raw)
        groups = self._matcher.match(self._all_quotes, self._pipeline_data["active_arb_types"])
        opps = self._scanner.scan(groups, self._pipeline_data["active_arb_types"])
        use_capital = self._pipeline_data["capital"] > 0
        if use_capital:
            old_cap = self._config.capital.amount_usd
            self._config.capital.amount_usd = self._pipeline_data["capital"]
            opps = self._filter.apply(opps)
            self._config.capital.amount_usd = old_cap
        else:
            opps = self._filter.apply(opps)
        self._opportunities = opps
        self._pipeline_data.update({
            "opportunity_count": len(opps),
            "total_pairs": len(self._all_quotes),
            "statuses": self._collector.source_statuses,
            "chain_counts": self._count_chains(self._all_quotes),
        })
        table = self.query_one(OpportunityTable)
        table.update_data(opps, use_capital)
        self.refresh()

    @staticmethod
    def _count_chains(quotes: list) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for q in quotes:
            counts[q.pair.chain] += 1
        return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))

    def action_toggle_arb(self) -> None:
        state = self._pipeline_data["active_arb_types"]
        if state == ["simple"]:
            self._pipeline_data["active_arb_types"] = ["simple", "triangular"]
        elif "triangular" in state and "cross_chain" not in state:
            self._pipeline_data["active_arb_types"] = ["simple", "triangular", "cross_chain"]
        elif "cross_chain" in state:
            self._pipeline_data["active_arb_types"] = ["simple"]
        self.query_one(ControlsBar).refresh()

    def action_change_sort(self) -> None:
        cols = ["profit", "spread", "age", "pair"]
        idx = cols.index(self._pipeline_data["sort_column"])
        self._pipeline_data["sort_column"] = cols[(idx + 1) % len(cols)]
        if self._opportunities:
            if self._pipeline_data["sort_column"] == "spread":
                self._opportunities.sort(key=lambda o: o.spread_pct, reverse=True)
            elif self._pipeline_data["sort_column"] == "age":
                self._opportunities.sort(key=lambda o: o.age_seconds)

    def action_set_capital(self) -> None:
        self.mount(InputCapital())
        self.query_one(InputCapital).focus()

    def action_force_refresh(self) -> None:
        asyncio.create_task(self._run_single_cycle())

    def action_toggle_help(self) -> None:
        self.mount(HelpOverlay())

    def action_increase_threshold(self) -> None:
        self._pipeline_data["min_profit"] += 1.0
        self._config.filters.min_profit_usd = self._pipeline_data["min_profit"]
        self.query_one(ControlsBar).refresh()

    def action_decrease_threshold(self) -> None:
        self._pipeline_data["min_profit"] = max(0, self._pipeline_data["min_profit"] - 1.0)
        self._config.filters.min_profit_usd = self._pipeline_data["min_profit"]
        self.query_one(ControlsBar).refresh()


class InputCapital(App[float | None]):
    CSS = """
    Screen { align: center middle; }
    Input { width: 30; }
    """

    def compose(self) -> ComposeResult:
        from textual.widgets import Input, Static
        yield Static("Enter capital amount in USD (0 to disable):")
        yield Input(placeholder="1000")

    def on_input_submitted(self, event) -> None:
        try:
            val = float(event.value)
        except ValueError:
            self.exit(None)
            return
        self.exit(val)


class HelpOverlay(App[None]):
    CSS = """
    Screen { align: center middle; }
    """

    def compose(self) -> ComposeResult:
        from textual.widgets import Static
        yield Static(
            "[bold]NASE Controls[/]\n\n"
            "q       Quit\n"
            "a       Toggle arbitrage types\n"
            "s       Change sort column\n"
            "c       Set capital amount\n"
            "+/-     Adjust min profit threshold ($1)\n"
            "r       Force refresh\n"
            "h       Show/hide this help\n"
            "Enter   Press Enter on any key to dismiss\n"
        )

    def on_key(self, event) -> None:
        self.exit(None)
```

- [ ] **Step 2: Commit**

```bash
cd NASE && git add -A && git commit -m "feat: TUI application with all widgets and keyboard controls"
```

---

### Task 19: Entry Point

**Files:**
- Create: `NASE/main.py`

- [ ] **Step 1: Write main.py**

```python
import sys
import asyncio

from util.config import load_config
from util.logging_config import setup_logging
from tui.app import NaseApp


def main() -> None:
    logger = setup_logging()
    logger.info("NASE starting")

    config = load_config()

    app = NaseApp(config)
    try:
        app.run()
    except KeyboardInterrupt:
        pass
    finally:
        logger.info("NASE shutting down")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify entry point runs (dry — no APIs needed)**

```bash
cd NASE && python -c "from main import main; print('Entry point OK')"
```
Expected: `Entry point OK`

- [ ] **Step 3: Commit**

```bash
cd NASE && git add -A && git commit -m "feat: CLI entry point with config loading and logging"
```

---

### Task 20: Run NASE

- [ ] **Step 1: Run NASE**

```bash
cd NASE && python main.py
```

Expected: TUI launches. Status bar shows sources connecting. Table may be empty if no API keys configured or rate-limited. Sources show health statuses. Press `q` to quit.

- [ ] **Step 2: Verify log output**

```bash
cd NASE && head -5 nase.log
```
Expected: JSON lines with `event: "NASE starting"`, source fetch results, etc.

- [ ] **Step 3: Verify no mock data**

```
Check the TUI: all data is from real API responses. No hardcoded prices. An empty table is valid if no profitable opportunities exist. Status bar must show real source health.
```

- [ ] **Step 4: Commit**

```bash
cd NASE && git add -A && git commit -m "feat: initial working NASE run"
```

---

## Post-Implementation Verification Checklist

- [ ] TUI displays without crashing on startup
- [ ] Header shows cycle time, pair count, opportunity count
- [ ] Controls bar shows arb type toggles, capital, threshold
- [ ] Status bar shows per-source health (green ✓ / red ✗ / yellow ⏳)
- [ ] Status bar shows chain-by-chain pair counts
- [ ] Table sorts by net profit descending
- [ ] Detail panel opens on Enter for selected row
- [ ] `q` quits cleanly (no hanging processes)
- [ ] `a` cycles arb types (SIMPLE → SIMPLE+TRI → ALL → SIMPLE)
- [ ] `+`/`-` adjusts min profit threshold
- [ ] `c` prompts for capital input
- [ ] `r` forces immediate cycle
- [ ] No mock data anywhere in the table
- [ ] `nase.log` has structured JSON-line entries
- [ ] `.env` API keys are functional (or sources gracefully report ✗)
- [ ] Config validation catches bad values at startup
