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
            "Ticket Diagnosis",
            "Suggested Epic",
            "Suggested Fix Version Group",
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
                t.ticket_diagnosis or "",
                t.suggested_epic or "",
                t.suggested_fix_version_group or "",
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
        
        # Ticket Diagnosis
        if t.ticket_diagnosis:
            lines.append("**Ticket Diagnosis:**")
            lines.append(t.ticket_diagnosis)
            lines.append("")
        
        # Suggested Epic
        if t.suggested_epic:
            lines.append(f"**Suggested Epic:** {t.suggested_epic}")
            lines.append("")
        
        # Suggested Fix Version Group
        if t.suggested_fix_version_group:
            lines.append(f"**Suggested Fix Version Group:** {t.suggested_fix_version_group}")
            lines.append("")
        
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def epic_audit_to_markdown(result: BulkRefinerResult) -> str:
    ea = result.epic_audit
    lines = []
    lines.append("## Epic Audit Summary")
    lines.append("")
    
    # Unassigned Tickets
    lines.append(f"**Unassigned Tickets:** {ea.unassigned_ticket_count} ({ea.percent_missing_epic:.1f}%)")
    lines.append("")
    
    # Recommended Epics
    lines.append("### Suggested Epics:")
    if ea.recommended_epics:
        for grp in ea.recommended_epics:
            lines.append(f"- **{grp.suggested_epic_name}**: {len(grp.tickets)} tickets")
            if grp.reason:
                lines.append(f"  - _Reason_: {grp.reason}")
            if grp.tickets:
                lines.append(f"  - Tickets: {', '.join(grp.tickets)}")
            lines.append("")
    else:
        lines.append("- None suggested")
        lines.append("")
    
    # Misaligned Tickets
    if ea.misaligned_tickets:
        lines.append("### Misaligned Assignments:")
        for mis in ea.misaligned_tickets:
            current_epic_str = mis.current_epic or "None"
            lines.append(f"- **{mis.issue_key}** assigned to `{current_epic_str}` but appears more aligned with **\"{mis.suggested_epic}\"**")
            if mis.reason:
                lines.append(f"  - _Reason_: {mis.reason}")
        lines.append("")
    
    lines.append(f"**Suggested total epics:** {ea.suggested_total_epics}")
    lines.append("")
    return "\n".join(lines).strip() + "\n"


def fix_versions_to_markdown(result: BulkRefinerResult) -> str:
    fv = result.fix_versions
    lines = []
    lines.append("## Fix Version Recommendations")
    lines.append("")
    if not fv.groups:
        lines.append("_No groups suggested._")
    else:
        for group in fv.groups:
            lines.append(f"### Proposed Fix Version: \"{group.name}\"")
            if group.rationale:
                lines.append(f"_Rationale_: {group.rationale}")
            lines.append("")
            lines.append("Tickets:")
            for ticket in group.tickets:
                lines.append(f"- {ticket}")
            lines.append("")
    return "\n".join(lines).strip() + "\n"


