from dataclasses import replace
from decimal import Decimal, DecimalException
from statistics import median
from typing import Iterable

from models.constants import KNOWN_TOKENS
from models.types import Pair, PriceQuote, Token

CHAIN_IDS: dict[str, int] = {
    "ethereum": 1,
    "optimism": 10,
    "bsc": 56,
    "polygon": 137,
    "arbitrum": 42161,
    "avalanche": 43114,
    "base": 8453,
    "zksync": 324,
    "linea": 59144,
}

KYBER_CHAIN_NAMES: dict[str, str] = {
    "ethereum": "ethereum",
    "optimism": "optimism",
    "bsc": "bsc",
    "polygon": "polygon",
    "arbitrum": "arbitrum",
    "avalanche": "avalanche",
    "base": "base",
    "zksync": "zksync",
    "linea": "linea",
}

MAX_QUOTE_TOKENS_PER_CHAIN = 1
EXECUTABLE_NOTIONALS_USD = (100, 1_000, 10_000)
MAX_EXECUTABLE_DEVIATION_PCT = Decimal("3.0")
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
QUOTE_USER_ADDRESS = "0x000000000000000000000000000000000000dEaD"
QUOTE_SYMBOLS = ("USDC", "USDT", "USDBC")


def token_decimals(token: dict[str, str]) -> int:
    try:
        return int(token.get("decimals", 18))
    except (TypeError, ValueError):
        return 18


def unit_amount(token: dict[str, str]) -> str:
    return str(10 ** token_decimals(token))


def quote_token_for_chain(chain: str) -> dict[str, str] | None:
    tokens = KNOWN_TOKENS.get(chain, [])
    for wanted in QUOTE_SYMBOLS:
        for token in tokens:
            if token.get("symbol", "").upper() == wanted:
                return token
    return None


def quote_jobs(chains: Iterable[str], limit_per_chain: int = MAX_QUOTE_TOKENS_PER_CHAIN) -> list[tuple[str, dict[str, str], dict[str, str]]]:
    jobs: list[tuple[str, dict[str, str], dict[str, str]]] = []
    for chain in chains:
        if chain not in CHAIN_IDS:
            continue
        quote = quote_token_for_chain(chain)
        if not quote:
            continue
        selected = 0
        for base in KNOWN_TOKENS.get(chain, []):
            if base["address"].lower() == quote["address"].lower():
                continue
            if base.get("symbol", "").upper() in QUOTE_SYMBOLS:
                continue
            jobs.append((chain, base, quote))
            selected += 1
            if selected >= limit_per_chain:
                break
    return jobs


def decimal_price_from_amounts(
    in_amount_raw: str | int,
    out_amount_raw: str | int,
    in_decimals: int,
    out_decimals: int,
) -> Decimal | None:
    try:
        in_units = Decimal(str(in_amount_raw)) / (Decimal(10) ** in_decimals)
        out_units = Decimal(str(out_amount_raw)) / (Decimal(10) ** out_decimals)
        if in_units <= 0 or out_units <= 0:
            return None
        return out_units / in_units
    except (DecimalException, ValueError, TypeError):
        return None


def make_quote(
    *,
    source_api: str,
    dex: str,
    chain: str,
    base_info: dict[str, str],
    quote_info: dict[str, str],
    price,
    liquidity_usd: float = 0.0,
    volume_24h_usd: float = 0.0,
    pair_suffix: str | None = None,
) -> PriceQuote | None:
    try:
        price_dec = Decimal(str(price))
        if price_dec <= 0:
            return None
        base = Token(
            address=base_info["address"],
            symbol=base_info.get("symbol", "???"),
            chain=chain,
            decimals=token_decimals(base_info),
        )
        quote = Token(
            address=quote_info["address"],
            symbol=quote_info.get("symbol", "???"),
            chain=chain,
            decimals=token_decimals(quote_info),
        )
        suffix = pair_suffix or f"{chain}:{base.address}:{quote.address}"
        return PriceQuote(
            pair=Pair(base=base, quote=quote, pair_address=f"{source_api}:{suffix}"),
            dex=dex,
            source_api=source_api,
            ask_price=price_dec,
            bid_price=price_dec,
            liquidity_usd=liquidity_usd,
            volume_24h_usd=volume_24h_usd,
        )
    except (KeyError, TypeError, ValueError, DecimalException):
        return None


def amount_for_notional_usd(base: dict[str, str], price: Decimal, notional_usd: int) -> str | None:
    if price <= 0:
        return None
    try:
        amount_units = Decimal(notional_usd) / price
        raw = int(amount_units * (Decimal(10) ** token_decimals(base)))
        if raw <= 0:
            return None
        return str(raw)
    except (DecimalException, ValueError, TypeError, OverflowError):
        return None


def _confidence_from_validation(deviations: list[Decimal], executable: bool) -> int:
    if not executable:
        return 55
    worst = max(deviations, default=Decimal("0"))
    score = 95 - int(min(worst, Decimal("10")) * 3)
    return max(60, min(98, score))


async def validate_executable_quote(source, chain, base, quote, quote_func, seed: PriceQuote) -> PriceQuote | None:
    if seed.mid_price <= 0:
        return None
    checks: list[PriceQuote] = []
    notes: list[str] = []
    for notional in EXECUTABLE_NOTIONALS_USD:
        if source.bucket_status["rate_limited"]:
            break
        amount = amount_for_notional_usd(base, seed.mid_price, notional)
        if not amount:
            notes.append(f"notional_{notional}:amount_unavailable")
            continue
        try:
            q = await quote_func(chain, base, quote, amount_raw=amount)
        except Exception:
            if source.bucket_status["rate_limited"]:
                notes.append(f"notional_{notional}:rate_limited")
                break
            notes.append(f"notional_{notional}:failed")
            continue
        if isinstance(q, PriceQuote):
            checks.append(replace(q, notional_usd=float(notional)))
    if len(checks) < 2:
        return replace(seed, executable=False, confidence_score=45, validation_notes=tuple(notes + ["exec_depth:insufficient"]))

    prices = [q.mid_price for q in checks if q.mid_price > 0]
    med = Decimal(str(median([float(p) for p in prices])))
    if med <= 0:
        return replace(seed, executable=False, confidence_score=45, validation_notes=tuple(notes + ["exec_depth:no_median"]))
    deviations = [abs(p - med) / med * Decimal("100") for p in prices]
    if max(deviations) > MAX_EXECUTABLE_DEVIATION_PCT:
        return replace(
            seed,
            executable=False,
            confidence_score=40,
            validation_notes=tuple(notes + [f"exec_depth:unstable_{max(deviations):.2f}%"]),
        )
    mid = checks[len(checks) // 2]
    return replace(
        mid,
        executable=True,
        confidence_score=_confidence_from_validation(deviations, True),
        validation_notes=tuple(notes + ["exec_depth:100/1000/10000"]),
    )


async def collect_quote_jobs(source, chains, quote_func) -> list[PriceQuote]:
    quotes: list[PriceQuote] = []
    for chain, base, quote in quote_jobs(chains):
        if source.bucket_status["rate_limited"]:
            break
        try:
            result = await quote_func(chain, base, quote)
        except Exception:
            if source.bucket_status["rate_limited"]:
                break
            continue
        if isinstance(result, PriceQuote):
            validated = await validate_executable_quote(source, chain, base, quote, quote_func, result)
            if isinstance(validated, PriceQuote):
                quotes.append(validated)
    return quotes
