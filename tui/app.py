import asyncio
import time
from collections import defaultdict

from textual.app import App, ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Footer

from tui.header import HeaderBar
from tui.controls import ControlsBar
from tui.table import OpportunityTable
from tui.detail import DetailPanel
from tui.status import StatusBar

from pipeline.collector import Collector
from pipeline.normalizer import Normalizer
from pipeline.matcher import Matcher
from pipeline.scanner import Scanner
from pipeline.filter import ResultFilter

from sources.dexscreener import DexScreenerSource
from sources.dexpaprika import DexPaprikaSource
from sources.swapapi import SwapApiSource

from util.config import Config

import logging

logger = logging.getLogger("nase")


class NaseApp(App):
    CSS = """
    Screen {
        layout: vertical;
    }
    #header { dock: top; }
    #controls { dock: top; }
    #main-table { height: 1fr; }
    #detail { dock: bottom; }
    #status { dock: bottom; }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("a", "toggle_arb", "Toggle Arb Type"),
        ("s", "change_sort", "Change Sort"),
        ("c", "set_capital", "Set Capital"),
        ("r", "force_refresh", "Force Refresh"),
        ("h", "toggle_help", "Help"),
        ("plus", "increase_threshold", "Increase Threshold"),
        ("minus", "decrease_threshold", "Decrease Threshold"),
        ("enter", "show_detail", "Show Detail"),
    ]

    def __init__(self, config: Config):
        super().__init__()
        self._config = config
        self._collector = Collector(config)
        self._normalizer = Normalizer(config)
        self._matcher = Matcher()
        self._scanner = Scanner(config)
        self._filter = ResultFilter(config)
        self._pipeline_data: dict = {
            "cycle_time": 0,
            "total_pairs": 0,
            "opportunity_count": 0,
            "statuses": {},
            "chain_counts": {},
            "active_arb_types": config.enabled_arb_types,
            "capital": config.capital.amount_usd,
            "min_profit": config.filters.min_profit_usd,
            "sort_column": "profit",
        }
        self._opportunities: list = []
        self._all_quotes: list = []
        self._cycle_task: asyncio.Task | None = None

    @property
    def pipeline_data(self) -> dict:
        return self._pipeline_data

    def compose(self) -> ComposeResult:
        yield HeaderBar(id="header")
        yield ControlsBar(id="controls")
        yield OpportunityTable(id="main-table")
        yield DetailPanel(id="detail")
        yield StatusBar(id="status")

    async def on_mount(self) -> None:
        self._setup_sources()
        self._pipeline_data["statuses"] = self._collector.source_statuses
        await self._collector.start_all()
        self._cycle_task = asyncio.create_task(self._run_cycles())

    async def on_unmount(self) -> None:
        if self._cycle_task:
            self._cycle_task.cancel()
        await self._collector.stop_all()

    def _setup_sources(self) -> None:
        import os

        if self._config.sources.get("dexscreener") and self._config.sources["dexscreener"].enabled:
            self._collector.register(
                DexScreenerSource(
                    self._config.sources["dexscreener"],
                    os.getenv("DEXSCREENER_API_KEY"),
                )
            )
        if self._config.sources.get("dexpaprika") and self._config.sources["dexpaprika"].enabled:
            self._collector.register(
                DexPaprikaSource(
                    self._config.sources["dexpaprika"],
                    os.getenv("DEXPAPRIKA_API_KEY"),
                )
            )
        if self._config.sources.get("swapapi") and self._config.sources["swapapi"].enabled:
            self._collector.register(
                SwapApiSource(
                    self._config.sources["swapapi"],
                    os.getenv("SWAPAPI_API_KEY"),
                )
            )

    async def _run_cycles(self) -> None:
        while True:
            cycle_start = time.monotonic()
            await self._run_single_cycle()
            elapsed = time.monotonic() - cycle_start
            self._pipeline_data["cycle_time"] = elapsed
            sleep_for = max(0, self._config.refresh_interval_seconds - elapsed)
            await asyncio.sleep(sleep_for)

    async def _run_single_cycle(self) -> None:
        raw = await self._collector.collect()
        self._all_quotes = self._normalizer.normalize_all(raw)
        groups = self._matcher.match(self._all_quotes, self._pipeline_data["active_arb_types"])
        opps = self._scanner.scan(groups, self._pipeline_data["active_arb_types"])
        use_capital = self._pipeline_data["capital"] > 0
        if use_capital:
            old_cap = self._config.capital.amount_usd
            self._config.capital.amount_usd = self._pipeline_data["capital"]
            opps = self._filter.apply(opps)
            self._config.capital.amount_usd = old_cap
        else:
            opps = self._filter.apply(opps)
        self._opportunities = opps
        self._pipeline_data.update(
            {
                "opportunity_count": len(opps),
                "total_pairs": len(self._all_quotes),
                "statuses": self._collector.source_statuses,
                "chain_counts": self._count_chains(self._all_quotes),
            }
        )
        table = self.query_one(OpportunityTable)
        table.update_data(opps, use_capital)
        self.query_one(HeaderBar).refresh()
        self.query_one(StatusBar).refresh()

    @staticmethod
    def _count_chains(quotes: list) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for q in quotes:
            counts[q.pair.chain] += 1
        return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))

    def action_toggle_arb(self) -> None:
        state = self._pipeline_data["active_arb_types"]
        if state == ["simple"]:
            self._pipeline_data["active_arb_types"] = ["simple", "triangular"]
        elif "triangular" in state and "cross_chain" not in state:
            self._pipeline_data["active_arb_types"] = ["simple", "triangular", "cross_chain"]
        elif "cross_chain" in state:
            self._pipeline_data["active_arb_types"] = ["simple"]
        self.query_one(ControlsBar).refresh()

    def action_change_sort(self) -> None:
        cols = ["profit", "spread", "age", "pair"]
        idx = cols.index(self._pipeline_data["sort_column"])
        self._pipeline_data["sort_column"] = cols[(idx + 1) % len(cols)]
        if self._opportunities:
            if self._pipeline_data["sort_column"] == "spread":
                self._opportunities.sort(key=lambda o: o.spread_pct, reverse=True)
            elif self._pipeline_data["sort_column"] == "age":
                self._opportunities.sort(key=lambda o: o.age_seconds)

    def action_show_detail(self) -> None:
        table = self.query_one(OpportunityTable)
        detail = self.query_one(DetailPanel)
        detail.hide_panel()
        if table.cursor_row is None:
            return
        try:
            pair_addr = table.get_row_at(table.cursor_row)[-1]
            for o in self._opportunities:
                if o.pair.pair_address == pair_addr:
                    matching_quotes = [q for q in self._all_quotes if q.pair.pair_address == pair_addr]
                    detail.show_opportunity(o, matching_quotes, self._pipeline_data["capital"])
                    return
        except Exception:
            pass

    def action_set_capital(self) -> None:
        self.push_screen(CapitalModal())

    def action_force_refresh(self) -> None:
        asyncio.create_task(self._run_single_cycle())

    def action_toggle_help(self) -> None:
        self.push_screen(HelpModal())

    def action_increase_threshold(self) -> None:
        self._pipeline_data["min_profit"] += 1.0
        self._config.filters.min_profit_usd = self._pipeline_data["min_profit"]
        self.query_one(ControlsBar).refresh()

    def action_decrease_threshold(self) -> None:
        self._pipeline_data["min_profit"] = max(0, self._pipeline_data["min_profit"] - 1.0)
        self._config.filters.min_profit_usd = self._pipeline_data["min_profit"]
        self.query_one(ControlsBar).refresh()


class CapitalModal(ModalScreen[float | None]):
    CSS = """
    CapitalModal {
        align: center middle;
    }
    CapitalModal Input {
        width: 30;
    }
    """

    def compose(self) -> ComposeResult:
        from textual.widgets import Input, Static

        yield Static("Enter capital amount in USD (0 to disable):")
        yield Input(placeholder="1000")

    def on_input_submitted(self, event) -> None:
        try:
            val = float(event.value)
            self.app._pipeline_data["capital"] = val
            self.app.query_one(ControlsBar).refresh()
        except ValueError:
            pass
        self.dismiss()


class HelpModal(ModalScreen[None]):
    CSS = """
    HelpModal {
        align: center middle;
    }
    """

    def compose(self) -> ComposeResult:
        from textual.widgets import Static

        yield Static(
            "[bold]NASE Controls[/]\n\n"
            "q       Quit\n"
            "a       Toggle arbitrage types\n"
            "s       Change sort column\n"
            "c       Set capital amount\n"
            "+/-     Adjust min profit threshold ($1)\n"
            "r       Force refresh\n"
            "h       Show/hide this help\n"
            "Enter   View detail for selected row\n"
            "Press any key to dismiss\n"
        )

    def on_key(self, event) -> None:
        self.dismiss(None)
