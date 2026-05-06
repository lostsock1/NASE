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
    confidence_score: int = 50
    executable: bool = False
    notional_usd: float = 0.0
    validation_notes: tuple[str, ...] = field(default_factory=tuple)
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
    buy_chain: str = ""
    sell_chain: str = ""
    sell_pair_address: str = ""
    liquidity_usd: float = 0.0
    confidence_score: int = 0
    validation_notes: tuple[str, ...] = field(default_factory=tuple)
    source_apis: list[str] = field(default_factory=list)
    detected_at: float = field(default_factory=time.time)

    @property
    def age_seconds(self) -> float:
        return time.time() - self.detected_at
