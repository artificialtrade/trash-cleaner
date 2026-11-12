from __future__ import annotations

import csv
from pathlib import Path

from mail_review.models import MessageRecord
from mail_review.services.csv_importer import load_messages_from_csv


DEMO_CSV = Path(__file__).resolve().parent.parent / "data" / "demo_messages.csv"


def load_demo_messages() -> list[MessageRecord]:
    """Return synthetic offline records for iCloud, Gmail, and Outlook accounts."""

    return load_messages_from_csv(DEMO_CSV)


def write_default_demo(path: str | Path) -> None:
    """Copy demo fixture to another path for experimentation."""

    source = DEMO_CSV
    destination = Path(path)
    with source.open("r", encoding="utf-8", newline="") as input_file:
        reader = csv.reader(input_file)
        with destination.open("w", encoding="utf-8", newline="") as output_file:
            writer = csv.writer(output_file)
            writer.writerows(reader)
