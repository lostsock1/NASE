from dataclasses import dataclass
from pathlib import Path
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
