from textual.widgets import Static


class StatusBar(Static):
    DEFAULT_CSS = """
    StatusBar {
        height: auto;
        padding: 0 1;
        color: $text-muted;
    }
    StatusBar .green { color: #22c55e; }
    StatusBar .red { color: #ef4444; }
    StatusBar .yellow { color: #eab308; }
    """

    def render(self) -> str:
        sources_text = self._render_sources()
        chains_text = self._render_chains()
        return f"SOURCES: {sources_text}\nCHAINS: {chains_text}"

    def _render_sources(self) -> str:
        statuses = self.app._pipeline_data.get("statuses", {})
        parts = []
        for name, info in statuses.items():
            if info["healthy"]:
                c429 = info.get("consecutive_429s", 0)
                if c429 > 0:
                    mark = f"[yellow]✓ {c429}x429[/]"
                else:
                    sr = info.get("success_rate", 100)
                    mark = f"[green]✓ {sr:.0f}%[/]"
            elif info.get("rate_limited"):
                wait = info.get("rate_wait_seconds", 0)
                c429 = info.get("consecutive_429s", 0)
                mark = f"[yellow]⏳ {wait:.0f}s ({c429}x429)[/]"
            else:
                mark = "[red]✗[/]"
            parts.append(f"{name} {mark}")
        return "  ".join(parts) if parts else "No sources"

    def _render_chains(self) -> str:
        chain_counts = self.app._pipeline_data.get("chain_counts", {})
        if not chain_counts:
            return "No data"
        parts = [f"{chain}({count})" for chain, count in chain_counts.items()]
        return " ".join(parts)
