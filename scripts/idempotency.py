"""Persistent idempotency tracking for webhook-style events."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


@dataclass
class IdempotencyStore:
    path: Path
    ttl_hours: int = 24

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write({})

    def seen(self, event_id: str) -> bool:
        store = self._prune(self._load())
        return event_id in store

    def mark(self, event_id: str) -> bool:
        store = self._prune(self._load())
        if event_id in store:
            return False

        store[event_id] = _utc_now().isoformat().replace("+00:00", "Z")
        self._write(store)
        return True

    def mark_or_reject(self, event_id: str) -> bool:
        return self.mark(event_id)

    def _load(self) -> dict[str, str]:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _prune(self, store: dict[str, str]) -> dict[str, str]:
        cutoff = _utc_now() - timedelta(hours=self.ttl_hours)
        fresh = {event_id: ts for event_id, ts in store.items() if _parse_timestamp(ts) >= cutoff}
        if fresh != store:
            self._write(fresh)
        return fresh

    def _write(self, store: dict[str, str]) -> None:
        with NamedTemporaryFile("w", delete=False, dir=self.path.parent, encoding="utf-8") as handle:
            json.dump(store, handle, indent=2, sort_keys=True)
            handle.write("\n")
            temp_path = Path(handle.name)
        temp_path.replace(self.path)
