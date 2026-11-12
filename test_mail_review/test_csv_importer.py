from pathlib import Path

from mail_review.services.csv_importer import load_messages_from_csv


def test_import_handles_utf8_bom(tmp_path: Path) -> None:
    csv_text = (
        "\ufeffMailbox scanned,Folder,Sender,Date,Subject\n"
        "Gmail Personal,INBOX,sender@example.com,2026-10-01 10:00:00,Hello\n"
    )
    file_path = tmp_path / "evidence.csv"
    file_path.write_text(csv_text, encoding="utf-8")

    messages = load_messages_from_csv(file_path)

    assert len(messages) == 1
    assert messages[0].account == "Gmail Personal"
    assert messages[0].sender_domain == "example.com"


def test_import_fills_defaults_for_missing_fields(tmp_path: Path) -> None:
    csv_text = "Mailbox scanned,Sender\nTest Account,NoAddress\n"
    file_path = tmp_path / "missing.csv"
    file_path.write_text(csv_text, encoding="utf-8")

    messages = load_messages_from_csv(file_path)

    assert len(messages) == 1
    assert messages[0].folder == "unknown"
    assert messages[0].subject == "(no subject)"
