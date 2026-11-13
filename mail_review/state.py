from __future__ import annotations

from dataclasses import dataclass, field

from mail_review.models import MessageRecord


@dataclass
class MessageSelectionState:
    active_account: str = "Demo"
    selected_keys: set[str] = field(default_factory=set)
    current_preview_key: str | None = None

    def toggle_message(self, message: MessageRecord) -> None:
        if message.message_key in self.selected_keys:
            self.selected_keys.remove(message.message_key)
        else:
            self.selected_keys.add(message.message_key)

    def select_visible(self, visible_messages: list[MessageRecord]) -> None:
        for message in visible_messages:
            self.selected_keys.add(message.message_key)

    def clear_selection(self) -> None:
        self.selected_keys.clear()

    def switch_account(self, account: str) -> None:
        self.active_account = account
        self.clear_selection()
        self.clear_preview()

    def clear_preview(self) -> None:
        self.current_preview_key = None

    def set_preview(self, message: MessageRecord | None) -> None:
        self.current_preview_key = message.message_key if message else None

    def counts(self, visible_messages: list[MessageRecord]) -> tuple[int, int, int]:
        total = len(self.selected_keys)
        visible_keys = {item.message_key for item in visible_messages}
        visible = len(self.selected_keys.intersection(visible_keys))
        hidden = max(total - visible, 0)
        return total, visible, hidden
