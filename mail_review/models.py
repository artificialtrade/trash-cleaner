from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from email.utils import parseaddr


@dataclass(frozen=True)
class MessageRecord:
    """Lightweight message record used by Milestone 1 UI and tests."""

    message_key: str
    provider: str
    account: str
    folder: str
    sender_name: str
    sender_email: str
    sender_domain: str
    subject: str
    to_value: str
    cc_value: str
    date_text: str
    received_at: datetime | None
    source: str = "offline"
    raw: dict[str, str] = field(default_factory=dict)

    @staticmethod
    def derive_sender_parts(sender_name: str, sender_email: str) -> tuple[str, str]:
        parsed_name, parsed_email = parseaddr(sender_email or sender_name)
        final_name = sender_name or parsed_name or parsed_email or "Unknown sender"
        final_email = parsed_email or sender_email or "unknown@example.invalid"
        domain = "unknown"
        if "@" in final_email:
            domain = final_email.rsplit("@", 1)[-1].strip().lower() or "unknown"
        return final_name, final_email, domain
