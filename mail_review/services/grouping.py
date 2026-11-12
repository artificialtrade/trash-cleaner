from __future__ import annotations

from collections import defaultdict

from mail_review.models import MessageRecord


def group_by_sender_domain(messages: list[MessageRecord]) -> dict[str, list[MessageRecord]]:
    groups: dict[str, list[MessageRecord]] = defaultdict(list)
    for message in messages:
        groups[message.sender_domain].append(message)

    return dict(sorted(groups.items(), key=lambda item: (-len(item[1]), item[0])))


def filter_messages(
    messages: list[MessageRecord],
    group_name: str | None,
    search_text: str,
) -> list[MessageRecord]:
    filtered = messages
    if group_name and group_name != "All sender domains":
        filtered = [item for item in filtered if item.sender_domain == group_name]

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
