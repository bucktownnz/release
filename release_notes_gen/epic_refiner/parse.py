"""CSV parsing and validation for Epic Pack Refiner."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple


REQUIRED_COLUMN_ALIASES: Dict[str, List[str]] = {
    "issue_key": ["issue key", "key"],
    "issue_type": ["issue type", "type"],
    "summary": ["summary", "issue summary", "title"],
    "description": ["description", "issue description", "details"],
    "parent_key": ["parent key", "parent"],
}

OPTIONAL_COLUMN_ALIASES: Dict[str, List[str]] = {
    "status": ["status"],
    "labels": ["labels", "components", "labels/components"],
    "story_points": ["story points", "story points estimate", "story point estimate", "points"],
    "priority": ["priority"],
    "assignee": ["assignee", "owner"],
    "created": ["created", "created date"],
    "updated": ["updated", "updated date", "last updated"],
}


@dataclass(slots=True)
class TicketRow:
    """Normalised representation of a Jira row."""

    key: str
    issue_type: str
    summary: str
    description: str
    parent_key: str
    status: str = ""
    labels: str = ""
    story_points: str = ""
    priority: str = ""
    assignee: str = ""
    created: str = ""
    updated: str = ""
    raw: Dict[str, str] = field(default_factory=dict)
    row_number: int = 0


@dataclass(slots=True)
class ExcludedRow:
    """Row excluded from processing with reason."""

    row_number: int
    key: str
    issue_type: str
    reason: str


@dataclass(slots=True)
class ParseResult:
    """Parsing result with validation metadata."""

    epic: TicketRow
    children: List[TicketRow]
    excluded_rows: List[ExcludedRow]
    warnings: List[str]
    stats: Dict[str, int]
    detected_columns: Dict[str, Optional[str]]


class EpicValidationError(ValueError):
    """Raised when epic pack validation fails."""


def _normalise_headers(headers: Iterable[str]) -> Dict[str, str]:
    """Map lowercase stripped headers to original names."""
    return {header.lower().strip(): header for header in headers}


def _resolve_column(
    header_map: Dict[str, str],
    aliases: List[str],
    override: Optional[str] = None,
) -> Optional[str]:
    """Resolve column name using override or alias list."""
    if override:
        override_key = override.lower().strip()
        if override_key in header_map:
            return header_map[override_key]
        raise EpicValidationError(f"Override column '{override}' not found in CSV headers")

    for alias in aliases:
        alias_key = alias.lower().strip()
        if alias_key in header_map:
            return header_map[alias_key]
    return None


def _read_csv_content(
    *,
    file_path: Optional[str],
    file_content: Optional[bytes],
) -> Tuple[List[Dict[str, str]], List[str]]:
    """Read CSV content into list of dict rows and header list."""
    if file_path and file_content:
        raise ValueError("Provide either file_path or file_content, not both")
    if not file_path and file_content is None:
        raise ValueError("Provide either file_path or file_content")

    if file_path:
        try:
            with open(file_path, "r", encoding="utf-8-sig", newline="") as fh:
                content = fh.read()
        except UnicodeDecodeError:
            with open(file_path, "r", encoding="utf-8", newline="") as fh:
                content = fh.read()
    else:
        try:
            content = file_content.decode("utf-8-sig")
        except UnicodeDecodeError:
            content = file_content.decode("utf-8")

    reader = csv.DictReader(io.StringIO(content))
    headers = reader.fieldnames or []
    if not headers:
        raise EpicValidationError("CSV file has no headers")

    rows: List[Dict[str, str]] = []
    for row in reader:
        rows.append({(k or "").strip(): (v or "").strip() for k, v in row.items()})
    return rows, headers


def _build_ticket_row(
    row: Dict[str, str],
    row_number: int,
    column_map: Dict[str, Optional[str]],
) -> TicketRow:
    """Create TicketRow from raw dictionary."""
    def get(col_key: str) -> str:
        column_name = column_map.get(col_key)
        if not column_name:
            return ""
        return row.get(column_name, "").strip()

    labels_value = get("labels")
    if labels_value and column_map.get("labels"):
        labels_value = ", ".join(part.strip() for part in labels_value.split(",") if part.strip())

    ticket = TicketRow(
        key=get("issue_key"),
        issue_type=get("issue_type"),
        summary=get("summary"),
        description=get("description"),
        parent_key=get("parent_key"),
        status=get("status"),
        labels=labels_value,
        story_points=get("story_points"),
        priority=get("priority"),
        assignee=get("assignee"),
        created=get("created"),
        updated=get("updated"),
        raw=row,
        row_number=row_number,
    )
    return ticket


def parse_epic_csv(
    *,
    file_path: Optional[str] = None,
    file_content: Optional[bytes] = None,
    column_overrides: Optional[Dict[str, str]] = None,
) -> ParseResult:
    """
    Load and validate a Jira CSV representing an epic and its child tickets.

    Raises:
        EpicValidationError: when validation fails (missing columns, multiple epics, etc.)
    """
    column_overrides = column_overrides or {}
    rows, headers = _read_csv_content(file_path=file_path, file_content=file_content)
    header_map = _normalise_headers(headers)

    column_map: Dict[str, Optional[str]] = {}
    missing_required: List[str] = []

    # Resolve required columns
    for key, aliases in REQUIRED_COLUMN_ALIASES.items():
        override = column_overrides.get(key)
        column_name = _resolve_column(header_map, aliases, override)
        column_map[key] = column_name
        if not column_name:
            missing_required.append(key.replace("_", " "))

    if missing_required:
        missing_pretty = ", ".join(missing_required)
        available = ", ".join(headers)
        raise EpicValidationError(
            f"Missing required columns: {missing_pretty}. Available columns: {available}"
        )

    # Resolve optional columns
    for key, aliases in OPTIONAL_COLUMN_ALIASES.items():
        override_key = column_overrides.get(key)
        column_map[key] = _resolve_column(header_map, aliases, override_key)

    tickets: List[TicketRow] = []
    excluded: List[ExcludedRow] = []
    warnings: List[str] = []

    epic_rows: List[TicketRow] = []

    for idx, row in enumerate(rows, start=2):  # account for header row
        ticket = _build_ticket_row(row, idx, column_map)

        if not ticket.summary and not ticket.description:
            warnings.append(f"Row {idx}: Empty summary and description; skipped.")
            continue

        if not ticket.issue_type:
            excluded.append(
                ExcludedRow(
                    row_number=idx,
                    key=ticket.key,
                    issue_type="",
                    reason="Missing Issue Type",
                )
            )
            continue

        if ticket.issue_type.lower() == "epic":
            epic_rows.append(ticket)
        else:
            tickets.append(ticket)

    if not epic_rows:
        raise EpicValidationError("No Epic row found in CSV.")
    if len(epic_rows) > 1:
        epic_keys = ", ".join(epic.key or f"(row {epic.row_number})" for epic in epic_rows)
        raise EpicValidationError(f"Multiple epic rows found: {epic_keys}. Expected exactly one.")

    epic_ticket = epic_rows[0]
    epic_key = epic_ticket.key
    if not epic_key:
        raise EpicValidationError("Epic row missing Issue key; cannot validate children.")

    valid_children: List[TicketRow] = []
    for ticket in tickets:
        if not ticket.parent_key:
            excluded.append(
                ExcludedRow(
                    row_number=ticket.row_number,
                    key=ticket.key,
                    issue_type=ticket.issue_type,
                    reason="Missing Parent key",
                )
            )
            continue

        if ticket.parent_key != epic_key:
            excluded.append(
                ExcludedRow(
                    row_number=ticket.row_number,
                    key=ticket.key,
                    issue_type=ticket.issue_type,
                    reason=f"Parent key '{ticket.parent_key}' does not match epic '{epic_key}'",
                )
            )
            continue

        valid_children.append(ticket)

    if not valid_children:
        raise EpicValidationError("No valid child tickets found for the epic.")

    stats = {
        "total_rows": len(rows),
        "epic_row_number": epic_ticket.row_number,
        "children_count": len(valid_children),
        "excluded_count": len(excluded),
    }

    detected_columns = {
        key: column_map.get(key)
        for key in [
            "issue_key",
            "issue_type",
            "summary",
            "description",
            "parent_key",
            "status",
            "labels",
            "story_points",
            "priority",
            "assignee",
            "created",
            "updated",
        ]
    }

    return ParseResult(
        epic=epic_ticket,
        children=valid_children,
        excluded_rows=excluded,
        warnings=warnings,
        stats=stats,
        detected_columns=detected_columns,
    )

