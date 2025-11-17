from __future__ import annotations

from release_notes_gen.bulk_refiner.types import RefinedTicket, BulkRefinerResult, EpicAudit, EpicSuggestion
from release_notes_gen.bulk_refiner.writer import (
    refined_tickets_to_csv,
    refined_tickets_to_markdown,
    epic_audit_to_markdown,
    fix_versions_to_markdown,
)
from release_notes_gen.bulk_refiner.types import FixVersionGroup, FixVersionRecommendation


def _sample_tickets():
    return [
        RefinedTicket(
            issue_key="CUS-1",
            refined_summary="Clear title",
            refined_description="Concise description.",
            acceptance_criteria=["Given X, when Y, then Z"],
            parent_key=None,
            fix_versions=["v1.0"],
        )
    ]


def test_refined_tickets_to_csv_and_md():
    tickets = _sample_tickets()
    csv_bytes = refined_tickets_to_csv(tickets)
    assert b"Issue Key" in csv_bytes
    md = refined_tickets_to_markdown(tickets)
    assert "## CUS-1 — Clear title" in md


def test_audit_and_fix_versions_markdown():
    tickets = _sample_tickets()
    audit = EpicAudit(
        percent_missing_epic=100.0,
        recommended_epics=[EpicSuggestion(suggested_epic_name="Platform", reason="Shared functionality", tickets=["CUS-1"])],
        suggested_total_epics=1,
        per_ticket_suggestions={"CUS-1": "Platform"},
    )
    fix = FixVersionRecommendation(groups=[FixVersionGroup(name="Q1 Enhancements", tickets=["CUS-1"], rationale="Same area")])
    result = BulkRefinerResult(refined=tickets, epic_audit=audit, fix_versions=fix)
    ea_md = epic_audit_to_markdown(result)
    assert "Missing Epic:" in ea_md
    fv_md = fix_versions_to_markdown(result)
    assert "Fix Version Recommendations" in fv_md


