from textual.widgets import Static


class HeaderBar(Static):
    DEFAULT_CSS = """
    HeaderBar {
        height: 1;
        background: $panel;
        color: $text;
        padding: 0 1;
    }
    """

    def render(self) -> str:
        cycle = self.app._pipeline_data.get("cycle_time", 0)
        pairs = self.app._pipeline_data.get("total_pairs", 0)
        opps = self.app._pipeline_data.get("opportunity_count", 0)
        return (
            f"NASE v0.1    Cycle: {cycle:.1f}s    "
            f"Pairs: {pairs:,}    Opportunities: {opps}    "
            f"[dim][q] quit[/]"
        )
