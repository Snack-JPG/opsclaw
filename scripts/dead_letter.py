"""Dead-letter capture for failed OpsClaw events."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path


@dataclass
class DeadLetterEntry:
    id: str
    source: str
    payload: dict
    error: str
    attempts: int
    firstAttempt: str
    lastAttempt: str
    correlationId: str | None = None


class DeadLetterQueue:
    """Append failed events to date-partitioned dead-letter files."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def capture(
        self,
        *,
        event_id: str,
        source: str,
        payload: dict,
        error: str,
        attempts: int,
        first_attempt: datetime,
        last_attempt: datetime | None = None,
        correlation_id: str | None = None,
    ) -> Path:
        entry = DeadLetterEntry(
            id=event_id,
            source=source,
            payload=payload,
            error=error,
            attempts=attempts,
            firstAttempt=self._format(first_attempt),
            lastAttempt=self._format(last_attempt or datetime.now(timezone.utc)),
            correlationId=correlation_id,
        )
        path = self._path_for_date(date.today())
        items = self._load(path)
        items.append(asdict(entry))
        path.write_text(f"{json.dumps(items, indent=2)}\n", encoding="utf-8")
        return path

    def _path_for_date(self, target_date: date) -> Path:
        return self.root / f"{target_date.isoformat()}.json"

    def _load(self, path: Path) -> list[dict]:
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _format(value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
