from __future__ import annotations

import csv
import io
from typing import Dict, Iterable, List, Optional, Tuple

from .types import TicketInput


REQUIRED_COLUMNS = [
    "issue key",
    "summary",
    "description",
    "parent key",
    "fix versions",
]


def _normalise_header(name: str) -> str:
    return (name or "").strip().lower()


def _ensure_required_columns(headers: Iterable[str]) -> Tuple[bool, List[str]]:
    lower_headers = {_normalise_header(h) for h in headers}
    missing = [col for col in REQUIRED_COLUMNS if col not in lower_headers]
    return len(missing) == 0, missing


def _coerce_fix_versions(value: Optional[str]) -> List[str]:
    if not value:
        return []
    # Split on comma or semicolon
    parts = [p.strip() for p in value.replace(";", ",").split(",")]
    return [p for p in parts if p]


def load_bulk_csv(
    file_bytes: bytes,
) -> Tuple[List[TicketInput], Dict[str, str]]:
    """
    Load and validate CSV for the Bulk Ticket Refiner.

    Returns:
        tickets: List of TicketInput
        detected_columns: mapping of canonical name -> actual header
    Raises:
        ValueError if required columns are missing or CSV is malformed.
    """
    try:
        text = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = file_bytes.decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("CSV appears to have no header row.")

    ok, missing = _ensure_required_columns(reader.fieldnames)
    if not ok:
        raise ValueError(
            f"Missing required columns: {', '.join(missing)}. "
            "Ensure the CSV contains Issue Key, Summary, Description, Parent Key, Fix Versions."
        )

    # Build a map from canonical -> actual header
    header_map: Dict[str, str] = {}
    lower_to_actual = {_normalise_header(h): h for h in reader.fieldnames}
    for canonical in REQUIRED_COLUMNS:
        header_map[canonical] = lower_to_actual[canonical]

    tickets: List[TicketInput] = []
    for row in reader:
        # Skip empty lines
        if not any((row.get(h) or "").strip() for h in reader.fieldnames):
            continue

        issue_key = (row.get(header_map["issue key"]) or "").strip()
        summary = (row.get(header_map["summary"]) or "").strip()
        description = (row.get(header_map["description"]) or "").strip()
        parent_key = (row.get(header_map["parent key"]) or "").strip() or None
        fix_versions_raw = row.get(header_map["fix versions"])
        fix_versions = _coerce_fix_versions(fix_versions_raw)

        tickets.append(
            TicketInput(
                issue_key=issue_key,
                summary=summary,
                description=description,
                parent_key=parent_key,
                fix_versions=fix_versions,
                raw={k: (row.get(k) or "") for k in reader.fieldnames},
            )
        )

    detected = {
        "Issue Key": header_map["issue key"],
        "Summary": header_map["summary"],
        "Description": header_map["description"],
        "Parent Key": header_map["parent key"],
        "Fix Versions": header_map["fix versions"],
    }
    return tickets, detected


