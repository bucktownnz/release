from __future__ import annotations

import types

from release_notes_gen.bulk_refiner.pipeline import run_bulk_refiner_pipeline, BulkRefinerConfig
from release_notes_gen.bulk_refiner import refine as refine_mod
from release_notes_gen.bulk_refiner import epic_audit as epic_mod
from release_notes_gen.bulk_refiner import fix_versions as fix_mod
from release_notes_gen.bulk_refiner.types import RefinedTicket, EpicAudit, EpicSuggestion, FixVersionRecommendation, FixVersionGroup


def test_pipeline_with_monkeypatch(monkeypatch):
    # Prepare a tiny CSV
    csv_bytes = (
        "Issue Key,Summary,Description,Parent Key,Fix Versions\n"
        "CUS-1,Do thing,Some description,,\n"
    ).encode("utf-8")

    # Monkeypatch refine_ticket to avoid LLM calls
    def fake_refine_ticket(project, ticket, model, max_tokens, temperature):
        return (
            RefinedTicket(
                issue_key=ticket.issue_key,
                refined_summary=f"[Refined] {ticket.summary}",
                refined_description=ticket.description or "",
                acceptance_criteria=["Not enough information provided"],
                parent_key=ticket.parent_key,
                fix_versions=ticket.fix_versions,
            ),
            "raw",
        )

    monkeypatch.setattr(refine_mod, "refine_ticket", lambda **kwargs: fake_refine_ticket(**kwargs))

    # Monkeypatch epic audit
    def fake_epic_audit(tickets, model, max_tokens, temperature):
        return (
            EpicAudit(
                percent_missing_epic=100.0,
                recommended_epics=[EpicSuggestion(suggested_epic_name="Group A", reason="Theme", tickets=[t.issue_key for t in tickets])],
                suggested_total_epics=1,
                per_ticket_suggestions={t.issue_key: "Group A" for t in tickets},
            ),
            "raw",
        )

    monkeypatch.setattr(epic_mod, "run_epic_audit", lambda **kwargs: fake_epic_audit(**kwargs))

    # Monkeypatch fix versions
    def fake_fix_versions(tickets, model, max_tokens, temperature):
        return (
            FixVersionRecommendation(groups=[FixVersionGroup(name="Bundle 1", tickets=[t.issue_key for t in tickets], rationale="Similar")]),
            "raw",
        )

    monkeypatch.setattr(fix_mod, "suggest_fix_version_groups", lambda **kwargs: fake_fix_versions(**kwargs))

    result, detected, errors = run_bulk_refiner_pipeline(
        file_bytes=csv_bytes,
        config=BulkRefinerConfig(project="CPS", model="gpt-4o-mini"),
    )

    assert detected["Issue Key"] == "Issue Key"
    assert not errors
    assert result.refined and result.refined[0].issue_key == "CUS-1"
    assert result.epic_audit.suggested_total_epics == 1
    assert result.fix_versions.groups and result.fix_versions.groups[0].name == "Bundle 1"


