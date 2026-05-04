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
        arb_simple = "[bold]SIMPLE[/bold]" if "simple" in arb else "[dim]SIMPLE[/dim]"
        arb_tri = "[bold]TRI[/bold]" if "triangular" in arb else "[dim]TRI[/dim]"
        arb_cross = "[bold]CROSS[/bold]" if "cross_chain" in arb else "[dim]CROSS[/dim]"
        capital = self.app._pipeline_data.get("capital", 0)
        cap_text = f"[bold]${capital:,.0f}[/bold]" if capital > 0 else "[dim]$0[/dim]"
        buy_mode = self.app._pipeline_data.get("buy_price_mode", "ask")
        sell_mode = self.app._pipeline_data.get("sell_price_mode", "bid")
        min_profit = self.app._pipeline_data.get("min_profit", 5.0)
        return (
            f"[bold]ARB:[/] {arb_simple} {arb_tri} {arb_cross}    "
            f"[bold]BUY:[/] [bold]{buy_mode}[/bold]  [bold]SELL:[/] [bold]{sell_mode}[/bold]    "
            f"[bold]CAPITAL:[/] {cap_text}    "
            f"[bold]MIN:[/] [bold]${min_profit:,.2f}[/bold]"
        )
