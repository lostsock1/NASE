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
