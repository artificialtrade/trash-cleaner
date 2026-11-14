from pathlib import Path

from mail_review.models import MessageRecord
from mail_review.services.action_log import ActionLog
from mail_review.services.simulated_actions import SimulatedTrashStore
from mail_review.services.grouping import group_by_sender


def _message(key: str, sender: str, account: str = "Demo") -> MessageRecord:
    name, email, domain = MessageRecord.derive_sender_parts("", sender)
    return MessageRecord(
        message_key=key,
        provider="demo",
        account=account,
        folder="Inbox",
        sender_name=name,
        sender_email=email,
        sender_domain=domain,
        subject=f"Subject {key}",
        to_value="me@example.com",
        cc_value="",
        date_text="2026-01-01",
        received_at=None,
        source="csv" if account == "CSV Import" else "offline",
    )


def test_sender_grouping_uses_email_address_and_summarizes_count() -> None:
    groups = group_by_sender([
        _message("1", "News@example.com"),
        _message("2", "news@example.com"),
        _message("3", "other@example.com"),
    ])

    assert list(groups) == ["news@example.com", "other@example.com"]
    assert groups["news@example.com"].count == 2


def test_simulated_trash_restore_and_undo_never_mark_csv_as_live(tmp_path: Path) -> None:
    message = _message("csv-1", "sender@example.com", "CSV Import")
    store = SimulatedTrashStore(ActionLog(tmp_path / "actions.json"))

    store.move_to_trash([message])
    assert message.message_key in store.trashed
    assert message.is_live is False
    assert store.undo() == [message]
    assert not store.trashed
    assert store.action_log.read()[0].status == "simulated"


def test_action_log_keeps_accounts_isolated(tmp_path: Path) -> None:
    log = ActionLog(tmp_path / "actions.json")
    log.append([_message("1", "a@example.com", "Demo")], "move-to-trash", "simulated")
    log.append([_message("2", "b@example.com", "CSV Import")], "move-to-trash", "simulated")

    entries = log.read()
    assert [entry.account for entry in entries] == ["Demo", "CSV Import"]
