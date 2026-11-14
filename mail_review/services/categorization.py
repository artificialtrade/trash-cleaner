from __future__ import annotations

from mail_review.models import MessageRecord


def categorize_message(sender: str, subject: str, folder: str) -> str:
    """Assign a review category using conservative sender/subject signals."""

    text = f"{sender} {subject} {folder}".lower()
    if any(term in text for term in ("unsubscribe", "newsletter", "sale", "offer", "deal", "promo")):
        return "Promotions"
    if any(term in text for term in ("social", "facebook", "instagram", "linkedin", "twitter")):
        return "Social"
    if any(term in text for term in ("invoice", "receipt", "bank", "payment", "statement", "order")):
        return "Finance"
    if any(term in text for term in ("meeting", "calendar", "project", "work", "office", "team")):
        return "Work"
    if any(term in text for term in ("alert", "security", "login", "password", "verify")):
        return "Alerts"
    return "Other"


def category_for(message: MessageRecord) -> str:
    return categorize_message(message.sender_email, message.subject, message.folder)
