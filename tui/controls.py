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
        capital = self.app._pipeline_data.get("capital", 0)
        cap_text = f"[bold]${capital:,.0f}[/bold]" if capital > 0 else "[dim]$0[/dim]"
        min_profit = self.app._pipeline_data.get("min_profit", 5.0)
        delay = self.app._pipeline_data.get("refresh_delay", 5)
        return (
            f"[bold]CAPITAL:[/] {cap_text}    "
            f"[bold]MIN:[/] [bold]${min_profit:,.2f}[/]    "
            f"[bold]REFRESH:[/] [bold]{delay}s[/]"
        )
