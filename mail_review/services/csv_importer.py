from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

from mail_review.models import MessageRecord
from mail_review.services.categorization import categorize_message


DATE_FORMATS = (
    "%Y-%m-%d %H:%M:%S%z",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
    "%d/%m/%Y %H:%M:%S",
    "%m/%d/%Y %H:%M:%S",
)


COLUMN_ALIASES = {
    "mailbox scanned": "account",
    "folder": "folder",
    "sender name (unverified)": "sender_name",
    "sender": "sender",
    "sender domain": "sender_domain",
    "date": "date",
    "subject": "subject",
    "to": "to",
    "cc": "cc",
    "read": "is_read",
    "is read": "is_read",
    "unread": "is_unread",
    "attachments": "has_attachments",
    "has attachments": "has_attachments",
    "message-id": "message_id",
    "message id": "message_id",
    "thread-id": "thread_id",
    "thread id": "thread_id",
}


def _parse_date(value: str) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    for fmt in DATE_FORMATS:
        try:
            parsed = datetime.strptime(text, fmt)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            continue
    return None


def _normalize_row(row: dict[str, str]) -> dict[str, str]:
    normalized = {}
    for key, value in row.items():
        normalized[key.strip().lower()] = (value or "").strip()
    return normalized


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "read"}


def _as_unread(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "unread"}


def load_messages_from_csv(path: str | Path) -> list[MessageRecord]:
    """Load historical email evidence CSV into message records."""

    records: list[MessageRecord] = []
    csv_path = Path(path)
    with csv_path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        for index, row in enumerate(reader):
            normalized = _normalize_row(row)
            mapped: dict[str, str] = {}
            for src, target in COLUMN_ALIASES.items():
                mapped[target] = normalized.get(src, "")

            sender_name, sender_email, derived_domain = MessageRecord.derive_sender_parts(
                mapped.get("sender_name", ""), mapped.get("sender", "")
            )
            sender_domain = mapped.get("sender_domain") or derived_domain
            received_at = _parse_date(mapped.get("date", ""))
            account = mapped.get("account", "") or "Imported account"
            folder = mapped.get("folder", "") or "unknown"
            subject = mapped.get("subject", "") or "(no subject)"

            message_key = f"csv:{csv_path.name}:{index}:{sender_email}:{mapped.get('date', '')}"
            records.append(
                MessageRecord(
                    message_key=message_key,
                    provider="csv-import",
                    account=account,
                    folder=folder,
                    sender_name=sender_name,
                    sender_email=sender_email,
                    sender_domain=sender_domain.lower(),
                    subject=subject,
                    to_value=mapped.get("to", ""),
                    cc_value=mapped.get("cc", ""),
                    date_text=mapped.get("date", ""),
                    received_at=received_at,
                    source="csv",
                    raw=row,
                    message_id=mapped.get("message_id", ""),
                    thread_id=mapped.get("thread_id", ""),
                    is_read=_as_bool(mapped.get("is_read", ""))
                    and not _as_unread(mapped.get("is_unread", "")),
                    has_attachments=_as_bool(mapped.get("has_attachments", "")),
                    category=categorize_message(sender_email, subject, folder),
                )
            )
    return records
