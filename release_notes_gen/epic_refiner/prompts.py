"""Prompt builders for the Epic Pack Refiner."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


TICKET_SYSTEM_PROMPT = (
    "You are the world’s best technical product manager. "
    "Be precise, outcome-focused, and concise. Do not invent facts; if information is missing, "
    "list pointed questions. Acceptance Criteria must use Given/When/Then. "
    "Tailor tone for Issue Type: Bug (repro & verification), Sub-task (inherits parent scope), "
    "Story/Task (user-facing outcomes). Respond in UK English."
)


EPIC_SYSTEM_PROMPT = (
    "You are the world’s best technical product manager. "
    "Produce a crisp epic narrative, outcome statement, epic-level AC (Given/When/Then), key risks, "
    "and constraints/NFRs if implied. Evaluate ambition: do the child tickets collectively deliver "
    "a meaningful outcome? If not, recommend bolder, higher-value slices. Respond in UK English."
)


MISSING_TICKETS_SYSTEM_PROMPT = (
    "Identify missing work items using a fixed checklist (tech readiness, monitoring/alerts, "
    "runbook/docs, analytics/events, rollout/feature flags, accessibility, unhappy paths, data "
    "migration). Do not duplicate existing tickets. Output mini stories."
)


GAP_ANALYSIS_SYSTEM_PROMPT = (
    "Aggregate questions across tickets into a concise action list grouped by ticket and by common theme."
)


EXAMPLE_BLOCK_TEMPLATE = "### EXAMPLE FORMAT START\n{example}\n### EXAMPLE FORMAT END"


def _wrap_example(example: Optional[str]) -> Optional[str]:
    if not example:
        return None
    return EXAMPLE_BLOCK_TEMPLATE.format(example=example.strip())


def _build_json_payload(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _append_squad_context(
    messages: List[Dict[str, str]], squad_context: Optional[str]
) -> None:
    if not squad_context:
        return
    squad_msg = {
        "role": "system",
        "content": (
            "Context about the squad that owns this work:\n"
            f"{squad_context}\n\n"
            "Align all outputs with this squad's mission, systems, responsibilities, "
            "and non-functional priorities. Suggest improvements or missing work that "
            "fit this squad, but do not invent facts not supported by the input."
        ),
    }
    # Insert immediately after the first system message if present; otherwise at start
    insert_at = 1 if messages and messages[0].get("role") == "system" else 0
    messages.insert(insert_at, squad_msg)


def build_ticket_messages(
    *,
    project: str,
    epic_title: str,
    ticket_payload: Dict[str, Any],
    example_format: Optional[str] = None,
    squad_context: Optional[str] = None,
) -> List[Dict[str, str]]:
    """Construct chat messages for ticket refinement."""
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": TICKET_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": _build_json_payload(
                {
                    "project": project,
                    "epic_title": epic_title,
                    "ticket": ticket_payload,
                }
            ),
        },
        {
            "role": "user",
            "content": (
                "Return JSON only with keys: title, summary, acceptance_criteria (list of objects "
                "with given/when/then), risks (list), test_ideas (list), questions (optional list). "
                "Use concise UK English. Do not include narrative or markdown outside the JSON."
            ),
        },
    ]

    _append_squad_context(messages, squad_context)

    example_block = _wrap_example(example_format)
    if example_block:
        messages.append(
            {
                "role": "user",
                "content": (
                    "If an EXAMPLE FORMAT is provided, match its structure and headings exactly; "
                    "otherwise use the default template.\n"
                    f"{example_block}"
                ),
            }
        )
    return messages


def build_epic_messages(
    *,
    project: str,
    epic_payload: Dict[str, Any],
    child_ticket_summaries: List[Dict[str, Any]],
    example_format: Optional[str] = None,
    squad_context: Optional[str] = None,
) -> List[Dict[str, str]]:
    """Construct chat messages for epic refinement."""
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": EPIC_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": _build_json_payload(
                {
                    "project": project,
                    "epic": epic_payload,
                    "child_ticket_summaries": child_ticket_summaries,
                }
            ),
        },
        {
            "role": "user",
            "content": (
                "Return JSON only with keys: epic_title, narrative, outcome, "
                "epic_acceptance_criteria (list of objects with given/when/then), risks (list), "
                "constraints_or_nfrs (list, allow empty), ambition_assessment. "
                "Use concise UK English. Do not add markdown outside the JSON."
            ),
        },
    ]

    _append_squad_context(messages, squad_context)

    example_block = _wrap_example(example_format)
    if example_block:
        messages.append(
            {
                "role": "user",
                "content": (
                    "If an EXAMPLE FORMAT is provided, match its structure and headings exactly; "
                    "otherwise use the default template.\n"
                    f"{example_block}"
                ),
            }
        )

    return messages


def build_missing_tickets_messages(
    *,
    epic_narrative: str,
    child_ticket_summaries: List[Dict[str, Any]],
    squad_context: Optional[str] = None,
) -> List[Dict[str, str]]:
    """Construct chat messages for missing ticket suggestions."""
    messages = [
        {"role": "system", "content": MISSING_TICKETS_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": _build_json_payload(
                {
                    "epic_narrative": epic_narrative,
                    "child_ticket_summaries": child_ticket_summaries,
                }
            ),
        },
        {
            "role": "user",
            "content": (
                "Return JSON only with key suggested_tickets, which is a list of objects with "
                "title, outcome, acceptance_criteria (list of Given/When/Then objects). "
                "Do not include markdown outside the JSON."
            ),
        },
    ]

    _append_squad_context(messages, squad_context)
    return messages


def build_gap_analysis_messages(
    *,
    ticket_results: List[Dict[str, Any]],
    squad_context: Optional[str] = None,
) -> List[Dict[str, str]]:
    """Construct chat messages for gap analysis aggregation."""
    messages = [
        {"role": "system", "content": GAP_ANALYSIS_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": _build_json_payload({"ticket_results": ticket_results}),
        },
        {
            "role": "user",
            "content": (
                "Return JSON only with keys actions_by_ticket (object mapping ticket key to list of actions) "
                "and themes (list of shared themes). No markdown outside the JSON."
            ),
        },
    ]

    _append_squad_context(messages, squad_context)
    return messages

