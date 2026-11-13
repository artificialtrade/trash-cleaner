from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from mail_review.models import MessageRecord


@dataclass(frozen=True)
class SenderGroup:
    """Messages and summary data for one sender email address."""

    sender_email: str
    sender_name: str
    messages: tuple[MessageRecord, ...]

    @property
    def count(self) -> int:
        return len(self.messages)

    @property
    def unread_count(self) -> int:
        return sum(not message.is_read for message in self.messages)

    @property
    def date_range(self) -> str:
        dates = [message.received_at for message in self.messages if message.received_at]
        if not dates:
            return "Unknown date"
        earliest, latest = min(dates), max(dates)
        if earliest.date() == latest.date():
            return earliest.strftime("%Y-%m-%d")
        return f"{earliest:%Y-%m-%d} to {latest:%Y-%m-%d}"

    @property
    def folders(self) -> tuple[str, ...]:
        return tuple(sorted({message.folder for message in self.messages}))


def group_by_sender(messages: list[MessageRecord]) -> dict[str, SenderGroup]:
    grouped: dict[str, list[MessageRecord]] = defaultdict(list)
    for message in messages:
        grouped[message.sender_key].append(message)
    return {
        key: SenderGroup(key, records[0].sender_name, tuple(records))
        for key, records in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0]))
    }


def group_by_sender_domain(messages: list[MessageRecord]) -> dict[str, list[MessageRecord]]:
    groups: dict[str, list[MessageRecord]] = defaultdict(list)
    for message in messages:
        groups[message.sender_domain].append(message)

    return dict(sorted(groups.items(), key=lambda item: (-len(item[1]), item[0])))


def filter_messages(
    messages: list[MessageRecord],
    group_name: str | None,
    search_text: str,
    *,
    folder: str | None = None,
    read_status: str = "all",
    attachments: str = "all",
    category: str = "All categories",
) -> list[MessageRecord]:
    filtered = messages
    if group_name and group_name not in {"All sender domains", "All senders"}:
        filtered = [
            item
            for item in filtered
            if item.sender_domain == group_name or item.sender_key == group_name
        ]
    if folder and folder != "All folders":
        filtered = [item for item in filtered if item.folder == folder]
    if read_status == "read":
        filtered = [item for item in filtered if item.is_read]
    elif read_status == "unread":
        filtered = [item for item in filtered if not item.is_read]
    if attachments == "with attachments":
        filtered = [item for item in filtered if item.has_attachments]
    elif attachments == "without attachments":
        filtered = [item for item in filtered if not item.has_attachments]
    if category and category != "All categories":
        filtered = [item for item in filtered if item.category == category]

    text = search_text.strip().lower()
    if not text:
        return filtered

    return [
        item
        for item in filtered
        if text in item.sender_name.lower()
        or text in item.sender_email.lower()
        or text in item.subject.lower()
        or text in item.account.lower()
        or text in item.folder.lower()
    ]
