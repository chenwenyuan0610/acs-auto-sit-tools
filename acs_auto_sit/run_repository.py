from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


class RunRepository:
    def __init__(self, root: Path):
        self.root = Path(root)

    def save(self, run: dict[str, Any]) -> dict[str, Any]:
        path = self._path(str(run.get("runId") or ""))
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(run, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(path)
        return run

    def load(self, run_id: str) -> dict[str, Any]:
        path = self._path(run_id)
        if not path.is_file():
            raise FileNotFoundError(run_id)
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or value.get("schemaVersion") != 1:
            raise ValueError(f"Unsupported saved run: {run_id}")
        return value

    def list(self) -> list[dict[str, Any]]:
        if not self.root.is_dir():
            return []
        items = []
        for path in self.root.glob("*.json"):
            try:
                run = self.load(path.stem)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            items.append(
                {
                    "runId": run["runId"],
                    "startedAt": run.get("startedAt", ""),
                    "finishedAt": run.get("finishedAt", ""),
                    "execution": run.get("execution", {}),
                    "summary": run.get("summary", {}),
                }
            )
        return sorted(
            items,
            key=lambda item: str(item.get("startedAt") or ""),
            reverse=True,
        )

    def _path(self, run_id: str) -> Path:
        if not RUN_ID_PATTERN.fullmatch(str(run_id or "")):
            raise ValueError("Invalid runId.")
        return self.root / f"{run_id}.json"
