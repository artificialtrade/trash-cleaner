from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from mail_review.models import MessageRecord


def app_data_dir() -> Path:
    """Return a per-user data directory outside the project checkout."""

    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if not base:
        base = os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
    directory = Path(base) / "TrashCleaner" / "mail-review"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


@dataclass(frozen=True)
class ActionEntry:
    account: str
    sender: str
    message_id: str
    date: str
    action: str
    status: str
    source: str


class ActionLog:
    """Small JSON action log persisted in the user's application data directory."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else app_data_dir() / "action-log.json"

    def append(self, messages: list[MessageRecord], action: str, status: str) -> None:
        entries = self.read()
        now = datetime.now(timezone.utc).isoformat()
        entries.extend(
            ActionEntry(
                account=message.account,
                sender=message.sender_email,
                message_id=message.message_id or message.message_key,
                date=now,
                action=action,
                status=status,
                source=message.source,
            )
            for message in messages
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps([asdict(entry) for entry in entries], indent=2), encoding="utf-8")

    def read(self) -> list[ActionEntry]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return [ActionEntry(**entry) for entry in data if isinstance(entry, dict)]
