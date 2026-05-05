from decimal import Decimal, DecimalException
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

MAX_QUOTE_TOKENS_PER_CHAIN = 4
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
