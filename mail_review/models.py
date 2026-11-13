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
    message_id: str = ""
    thread_id: str = ""
    is_read: bool = False
    has_attachments: bool = False
    body_text: str = ""

    @property
    def is_live(self) -> bool:
        """Return whether this record represents a real mailbox message."""

        return self.source == "live"

    @property
    def sender_key(self) -> str:
        """Return the normalized sender email used for grouping."""

        return self.sender_email.strip().lower()

    @staticmethod
    def derive_sender_parts(sender_name: str, sender_email: str) -> tuple[str, str]:
        parsed_name, parsed_email = parseaddr(sender_email or sender_name)
        final_name = sender_name or parsed_name or parsed_email or "Unknown sender"
        final_email = parsed_email or sender_email or "unknown@example.invalid"
        domain = "unknown"
        if "@" in final_email:
            domain = final_email.rsplit("@", 1)[-1].strip().lower() or "unknown"
        return final_name, final_email, domain
