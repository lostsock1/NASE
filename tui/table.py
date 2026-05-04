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
