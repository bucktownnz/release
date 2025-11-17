from __future__ import annotations

import csv
import io
from typing import List

from .types import BulkRefinerResult, RefinedTicket


def refined_tickets_to_csv(tickets: List[RefinedTicket]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "Issue Key",
            "Refined Summary",
            "Refined Description",
            "Acceptance Criteria",
            "Parent Key",
            "Fix Versions",
        ]
    )
    for t in tickets:
        writer.writerow(
            [
                t.issue_key,
                t.refined_summary,
                t.refined_description,
                " | ".join(t.acceptance_criteria),
                t.parent_key or "",
                ", ".join(t.fix_versions),
            ]
        )
    return buffer.getvalue().encode("utf-8")


def refined_tickets_to_markdown(tickets: List[RefinedTicket]) -> str:
    lines = []
    for t in tickets:
        lines.append(f"## {t.issue_key} — {t.refined_summary}")
        lines.append("")
        lines.append(t.refined_description or "_No description_")
        lines.append("")
        lines.append("Acceptance Criteria:")
        if t.acceptance_criteria:
            for ac in t.acceptance_criteria:
                lines.append(f"- {ac}")
        else:
            lines.append("- Not enough information provided")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def epic_audit_to_markdown(result: BulkRefinerResult) -> str:
    ea = result.epic_audit
    lines = []
    lines.append(f"Missing Epic: {ea.percent_missing_epic:.1f}%")
    lines.append("")
    lines.append("Recommended Epics:")
    if ea.recommended_epics:
        for grp in ea.recommended_epics:
            lines.append(f"- {grp.suggested_epic_name} ({len(grp.tickets)} tickets)")
            if grp.reason:
                lines.append(f"  - Reason: {grp.reason}")
            if grp.tickets:
                lines.append(f"  - Tickets: {', '.join(grp.tickets)}")
    else:
        lines.append("- None suggested")
    lines.append("")
    lines.append(f"Suggested total epics: {ea.suggested_total_epics}")
    lines.append("")
    return "\n".join(lines).strip() + "\n"


def fix_versions_to_markdown(result: BulkRefinerResult) -> str:
    fv = result.fix_versions
    lines = []
    lines.append("Fix Version Recommendations")
    lines.append("")
    if not fv.groups:
        lines.append("_No groups suggested._")
    else:
        for group in fv.groups:
            lines.append(f"### {group.name}")
            if group.rationale:
                lines.append(f"_Rationale_: {group.rationale}")
            lines.append(f"Tickets: {', '.join(group.tickets)}")
            lines.append("")
    return "\n".join(lines).strip() + "\n"


