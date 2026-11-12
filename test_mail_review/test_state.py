from mail_review.models import MessageRecord
from mail_review.state import MessageSelectionState


def _message(key: str) -> MessageRecord:
    return MessageRecord(
        message_key=key,
        provider="demo",
        account="acc",
        folder="Inbox",
        sender_name="sender",
        sender_email="sender@example.com",
        sender_domain="example.com",
        subject="subject",
        to_value="",
        cc_value="",
        date_text="2026-01-01",
        received_at=None,
    )


def test_counts_report_hidden_selection() -> None:
    state = MessageSelectionState()
    visible = [_message("1"), _message("2")]

    state.select_visible(visible)
    state.toggle_message(_message("3"))

    total, visible_count, hidden = state.counts(visible)
    assert (total, visible_count, hidden) == (3, 2, 1)


def test_preview_clears_when_requested() -> None:
    state = MessageSelectionState()
    message = _message("a")

    state.set_preview(message)
    assert state.current_preview_key == "a"

    state.clear_preview()
    assert state.current_preview_key is None
