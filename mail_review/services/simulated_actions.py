from __future__ import annotations

from dataclasses import dataclass, field

from mail_review.models import MessageRecord
from mail_review.services.action_log import ActionLog


@dataclass
class SimulatedTrashStore:
    """Safe offline trash store; it never changes a real mailbox."""

    action_log: ActionLog = field(default_factory=ActionLog)
    trashed: dict[str, MessageRecord] = field(default_factory=dict)
    last_batch: list[str] = field(default_factory=list)

    def move_to_trash(self, messages: list[MessageRecord]) -> list[MessageRecord]:
        self.last_batch = [message.message_key for message in messages]
        for message in messages:
            self.trashed[message.message_key] = message
        self.action_log.append(messages, "move-to-trash", "simulated")
        return messages

    def restore(self, keys: list[str]) -> list[MessageRecord]:
        restored = [self.trashed.pop(key) for key in keys if key in self.trashed]
        self.action_log.append(restored, "restore", "simulated")
        return restored

    def undo(self) -> list[MessageRecord]:
        return self.restore(self.last_batch)
