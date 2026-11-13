from mail_review.services.categorization import categorize_message


def test_categorization_places_promotional_messages_in_promotions() -> None:
    assert categorize_message("offers@example.com", "Special sale offer", "Inbox") == "Promotions"


def test_categorization_places_security_messages_in_alerts() -> None:
    assert categorize_message("security@example.com", "New login alert", "Inbox") == "Alerts"
