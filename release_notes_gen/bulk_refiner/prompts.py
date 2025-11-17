from __future__ import annotations

from typing import Dict, List, Optional


def build_ticket_refine_messages(
    *,
    project: str,
    ticket: Dict[str, str],
) -> List[Dict[str, str]]:
    system = (
        "You are an expert Jira ticket refiner. Rewrite titles and descriptions to be clear, "
        "specific and actionable. Keep outputs concise. Respond ONLY with JSON with keys: "
        "refined_summary, refined_description, acceptance_criteria (array of strings)."
    )
    user = (
        f"Project: {project}\n"
        f"Issue Key: {ticket.get('issue_key')}\n"
        f"Summary: {ticket.get('summary')}\n"
        f"Description:\n{ticket.get('description')}\n\n"
        "Return JSON with these keys:\n"
        "{\n"
        '  "refined_summary": "clear, specific title",\n'
        '  "refined_description": "concise description",\n'
        '  "acceptance_criteria": ["Given/When/Then bullets or short points"]\n'
        "}\n"
        "If insufficient information for acceptance criteria, add one bullet: "
        '"Not enough information provided".'
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def build_epic_suggestion_messages(
    *,
    tickets: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    system = (
        "You cluster tickets into sensible epic groupings based on functionality. "
        "Respond ONLY with JSON: {"
        '"per_ticket_suggestions": {"ISSUE-1": "Epic Name" | null, ...}, '
        '"recommended_epics": [{"name": "Epic Name", "tickets": ["ISS-1", ...], "reason": "why"}], '
        '"suggested_total_epics": 3'
        "}"
    )
    bullets = "\n".join(
        f"- {t.get('issue_key')}: {t.get('refined_summary') or t.get('summary')}"
        for t in tickets
    )
    user = (
        "Cluster these tickets by theme into sensible epic groupings. "
        "Return JSON as specified.\n"
        f"Tickets:\n{bullets}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def build_fix_version_grouping_messages(
    *,
    tickets: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    system = (
        "Group tickets that could be released together by functional similarity. "
        "Propose short, descriptive group names. Respond ONLY with JSON: "
        '{"groups":[{"name":"Q1 Platform Enhancements","tickets":["ISS-1","ISS-2"],"rationale":"..."}]}'
    )
    bullets = "\n".join(
        f"- {t.get('issue_key')}: {t.get('refined_summary') or t.get('summary')}"
        for t in tickets
    )
    user = f"Propose release groups with names and rationale.\nTickets:\n{bullets}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


