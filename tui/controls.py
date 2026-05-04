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
