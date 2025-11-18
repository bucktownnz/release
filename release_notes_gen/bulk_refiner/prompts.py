from __future__ import annotations

from typing import Dict, List, Optional


def build_ticket_refine_messages(
    *,
    project: str,
    ticket: Dict[str, str],
) -> List[Dict[str, str]]:
    system = (
        "You are an expert Jira ticket analyst and refiner. Your role is to act as a domain-aware analyst "
        "that helps clean, group, and assess Jira tickets. You should:\n"
        "1. Rewrite titles and descriptions to be clear, specific and actionable\n"
        "2. Diagnose what's missing, unclear, or needs improvement in the ticket\n"
        "3. Suggest better Epic assignments if the current one is missing or incorrect\n"
        "4. Suggest logical Fix Version groupings based on functional area, shared system, or release intent\n\n"
        "Respond ONLY with JSON. Be thorough in your diagnosis - identify missing information, vague language, "
        "unclear purpose, or lack of context. Coach the user by explaining what's wrong and how to improve."
    )
    current_epic = ticket.get('parent_key') or 'None'
    user = (
        f"Project: {project}\n"
        f"Issue Key: {ticket.get('issue_key')}\n"
        f"Current Epic: {current_epic}\n"
        f"Summary: {ticket.get('summary')}\n"
        f"Description:\n{ticket.get('description')}\n\n"
        "Return JSON with these keys:\n"
        "{\n"
        '  "refined_summary": "clear, specific title",\n'
        '  "refined_description": "concise description",\n'
        '  "acceptance_criteria": ["Given/When/Then bullets or short points"],\n'
        '  "ticket_diagnosis": "Identify missing information, vague language, unclear purpose, or lack of context. Be specific about what needs improvement.",\n'
        '  "suggested_epic": "Suggested Epic name if current Epic is missing or incorrect, otherwise null",\n'
        '  "suggested_fix_version_group": "Suggested Fix Version group name based on functional area, shared system, or release intent"\n'
        "}\n"
        "If insufficient information for acceptance criteria, add one bullet: "
        '"Not enough information provided".\n'
        "For ticket_diagnosis, be specific: identify what context is missing, what language is vague, "
        "or what makes the purpose unclear. If the ticket is well-written, say so."
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def build_epic_suggestion_messages(
    *,
    tickets: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    system = (
        "You are an expert at analyzing Jira ticket-to-epic mappings. Your task is to:\n"
        "1. Evaluate whether tickets are correctly grouped under their current Epics\n"
        "2. Identify tickets without Parent Keys (Epics)\n"
        "3. Identify tickets that appear misgrouped under incorrect Epics\n"
        "4. Propose a recommended set of Epics with thematic clusters\n"
        "5. Suggest reassignments for misaligned tickets\n\n"
        "Use natural language understanding to assess functional alignment, not just string matching.\n"
        "Respond ONLY with JSON: {"
        '"per_ticket_suggestions": {"ISSUE-1": "Epic Name" | null, ...}, '
        '"recommended_epics": [{"name": "Epic Name", "tickets": ["ISS-1", ...], "reason": "why"}], '
        '"suggested_total_epics": 3, '
        '"misaligned_tickets": [{"issue_key": "ISS-1", "current_epic": "EPIC-1" | null, "suggested_epic": "Better Epic", "reason": "why misaligned"}], '
        '"unassigned_count": 24'
        "}"
    )
    bullets = []
    for t in tickets:
        issue_key = t.get('issue_key', '')
        current_epic = t.get('parent_key') or 'None'
        summary = t.get('refined_summary') or t.get('summary', '')
        description = t.get('refined_description', '')
        if description:
            bullets.append(f"- {issue_key} (Current Epic: {current_epic}): {summary}\n  Description: {description}")
        else:
            bullets.append(f"- {issue_key} (Current Epic: {current_epic}): {summary}")
    bullets_str = "\n".join(bullets)
    user = (
        "Analyze these tickets and their Epic assignments. Evaluate ticket-to-epic mapping, "
        "identify misgrouped tickets, and propose better groupings.\n\n"
        "For each ticket, consider:\n"
        "- Does it belong to its current Epic based on functional alignment?\n"
        "- If it has no Epic, what Epic should it belong to?\n"
        "- If it's misaligned, what Epic would be better?\n\n"
        "Return JSON as specified with recommended Epics, misaligned tickets, and unassigned count.\n"
        f"Tickets:\n{bullets_str}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def build_fix_version_grouping_messages(
    *,
    tickets: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    system = (
        "You are an expert at analyzing Jira tickets to propose logical Fix Version groupings for releases. "
        "Your task is to:\n"
        "1. IGNORE existing Fix Versions - analyze ticket content from scratch\n"
        "2. Group tickets by:\n"
        "   - Shared system or component\n"
        "   - Functional area (e.g., payments, authentication, data model)\n"
        "   - Release intent (e.g., technical debt, feature rollout, bug patching, platform stability)\n"
        "3. Propose meaningful Fix Version group names that reflect functional or release-oriented groupings\n"
        "4. Use natural language understanding to identify thematic clusters\n\n"
        "The groupings should be meaningful for release planning, not just shallow string matching.\n"
        "Respond ONLY with JSON: "
        '{"groups":[{"name":"Q4 – Platform Stability","tickets":["ISS-1","ISS-2"],"rationale":"why these belong together"}]}'
    )
    bullets = []
    for t in tickets:
        issue_key = t.get('issue_key', '')
        summary = t.get('refined_summary') or t.get('summary', '')
        description = t.get('refined_description', '')
        if description:
            bullets.append(f"- {issue_key}: {summary}\n  Description: {description}")
        else:
            bullets.append(f"- {issue_key}: {summary}")
    bullets_str = "\n".join(bullets)
    
    user = (
        "Analyze these tickets and propose logical Fix Version groupings based on functional clustering. "
        "Ignore any existing Fix Versions - analyze the ticket content to group by shared system, "
        "functional area, or release intent.\n\n"
        "Propose new Fix Version group names and associated tickets. "
        "Each group should represent tickets that make sense to release together.\n\n"
        f"Tickets:\n{bullets_str}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


