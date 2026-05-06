from textual.widgets import DataTable
from textual.message import Message
from decimal import Decimal

from models.types import Opportunity


class OpportunityTable(DataTable):
    DEFAULT_CSS = """
    OpportunityTable {
        height: 1fr;
    }
    """

    BINDINGS = [
        ("enter", "request_detail", "Detail"),
    ]

    class DetailRequested(Message):
        """Posted when Enter is pressed on a row."""
        def __init__(self, row_key: str) -> None:
            self.row_key = row_key
            super().__init__()

    def on_mount(self) -> None:
        self.cursor_type = "row"
        self.add_columns("#", "Coin", "Pair", "Src Ch", "Buy At", "Sell At", "Rcv Ch", "TVL", "Buy $", "Sell $", "Spread", "Conf", "Profit", "Age")

    def action_request_detail(self) -> None:
        if self.cursor_row is not None and self.row_count > 0:
            try:
                key = self.ordered_rows[self.cursor_row].key
                self.post_message(self.DetailRequested(key))
            except Exception:
                pass

    def update_data(self, opportunities: list[Opportunity], use_capital: bool) -> None:
        selected_key: str | None = None
        if self.cursor_row is not None and self.row_count > 0:
            try:
                selected_key = self.ordered_rows[self.cursor_row].key
            except Exception:
                pass
        cursor_idx: int = self.cursor_row if self.row_count > 0 else 0

        for key in [r.key for r in reversed(self.ordered_rows)]:
            self.remove_row(key)

        for i, o in enumerate(opportunities, 1):
            age = f"{o.age_seconds:.0f}s"
            src_chain = o.buy_chain.title()
            rcv_chain = o.sell_chain.title()
            tvl_str = _fmt_tvl(o.liquidity_usd)
            buy_str = _fmt_price(o.buy_price)
            sell_str = _fmt_price(o.sell_price)
            if use_capital and o.net_profit_usd > 0:
                profit = f"${o.net_profit_usd:,.2f}"
            elif not use_capital:
                profit = f"({o.spread_pct:.2f}%)"
            else:
                profit = f"${o.net_profit_usd:,.2f}"

            spread_color = self._spread_style(o.spread_pct, o.age_seconds)
            self.add_row(
                str(i),
                o.pair.base.symbol,
                f"{o.pair.base.symbol}/{o.pair.quote.symbol}",
                src_chain,
                o.buy_at_dex[:20],
                o.sell_at_dex[:20],
                rcv_chain,
                tvl_str,
                buy_str,
                sell_str,
                spread_color,
                self._confidence_style(o.confidence_score),
                profit,
                age,
                key=o.pair.pair_address,
            )

        if selected_key is not None and self.row_count > 0:
            for row_idx in range(self.row_count):
                try:
                    if self.ordered_rows[row_idx].key == selected_key:
                        self.move_cursor(row=row_idx, animate=False)
                        return
                except Exception:
                    pass

        if self.row_count > 0:
            target = min(cursor_idx, self.row_count - 1)
            self.move_cursor(row=target, animate=False)

    @staticmethod
    def _confidence_style(score: int) -> str:
        if score >= 80:
            return f"[#22c55e]{score}[/]"
        if score >= 60:
            return f"[#eab308]{score}[/]"
        return f"[#ef4444]{score}[/]"

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


def _fmt_price(p: Decimal) -> str:
    f = float(p)
    if f >= 1:
        return f"${f:,.2f}"
    if f >= 0.01:
        return f"${f:,.4f}"
    return f"${f:,.6f}"


def _fmt_tvl(v: float) -> str:
    if v <= 0:
        return "$0"
    if v >= 1_000_000:
        return f"${v/1_000_000:,.1f}M"
    if v >= 1_000:
        return f"${v/1_000:,.0f}K"
    return f"${v:,.0f}"
