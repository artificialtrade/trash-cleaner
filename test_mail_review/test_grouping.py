from mail_review.models import MessageRecord
from mail_review.services.grouping import filter_messages, group_by_sender_domain


def _message(key: str, domain: str, subject: str, account: str = "A") -> MessageRecord:
    return MessageRecord(
        message_key=key,
        provider="demo",
        account=account,
        folder="Inbox",
        sender_name="Sender",
        sender_email=f"sender@{domain}",
        sender_domain=domain,
        subject=subject,
        to_value="to@example.com",
        cc_value="",
        date_text="2026-01-01",
        received_at=None,
    )


def test_grouping_counts_by_domain() -> None:
    grouped = group_by_sender_domain(
        [_message("1", "one.example", "A"), _message("2", "one.example", "B"), _message("3", "two.example", "C")]
    )

    assert list(grouped.keys())[0] == "one.example"
    assert len(grouped["one.example"]) == 2
    assert len(grouped["two.example"]) == 1


def test_filter_respects_group_and_search() -> None:
    messages = [
        _message("1", "one.example", "Billing update", "Gmail"),
        _message("2", "two.example", "Travel notice", "Outlook"),
    ]

    filtered = filter_messages(messages, "one.example", "billing")

    assert len(filtered) == 1
    assert filtered[0].message_key == "1"
