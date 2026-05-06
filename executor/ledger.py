from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class AuditLedger:
    def __init__(self, path: str):
        self.path = Path(path)

    def append(self, record: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, separators=(",", ":"), default=str))
            handle.write("\n")

    def latest(self, limit: int = 100) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()[-limit:]
        records = []
        for line in lines:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return records

    def reserved_today_usd(self) -> float:
        total = 0.0
        for record in self.latest(1000):
            if record.get("status") in {"accepted_dry_run", "accepted_executor_ready"}:
                total += float(record.get("intent", {}).get("budget_usd") or 0)
        return total

