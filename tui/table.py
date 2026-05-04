from textual.widgets import DataTable
from decimal import Decimal

from models.types import Opportunity


class OpportunityTable(DataTable):
    DEFAULT_CSS = """
    OpportunityTable {
        height: 1fr;
    }
    """

    def on_mount(self) -> None:
        self.cursor_type = "row"
        self.add_columns("#", "Pair", "Src Ch", "Buy At", "Sell At", "Rcv Ch", "Buy $", "Sell $", "Spread", "Profit", "Age")

    def update_data(self, opportunities: list[Opportunity], use_capital: bool) -> None:
        self.clear()
        for i, o in enumerate(opportunities, 1):
            age = f"{o.age_seconds:.0f}s"
            src_chain = o.buy_chain.title()
            rcv_chain = o.sell_chain.title()
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
                f"{o.pair.base.symbol}/{o.pair.quote.symbol}",
                src_chain,
                o.buy_at_dex,
                o.sell_at_dex,
                rcv_chain,
                buy_str,
                sell_str,
                spread_color,
                profit,
                age,
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


def _fmt_price(p: Decimal) -> str:
    f = float(p)
    if f >= 1:
        return f"${f:,.2f}"
    if f >= 0.01:
        return f"${f:,.4f}"
    return f"${f:,.6f}"
