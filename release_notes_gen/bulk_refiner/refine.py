from __future__ import annotations

import json
from typing import Dict, List, Tuple

from release_notes_gen.llm import chat_completion
from .prompts import build_ticket_refine_messages
from .types import RefinedTicket, TicketInput


def _parse_json(text: str) -> Dict:
    """Parse JSON from an LLM response, tolerating extra chatter and code fences."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()

    try:
        return json.loads(stripped)
    except Exception:
        pass

    in_string = False
    escape = False
    depth = 0
    start_index = None

    for idx, ch in enumerate(stripped):
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            if depth == 0:
                start_index = idx
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start_index is not None:
                candidate = stripped[start_index : idx + 1]
                try:
                    return json.loads(candidate)
                except Exception:
                    start_index = None

    raise json.JSONDecodeError("Could not find valid JSON object in response", stripped, 0)


def refine_ticket(
    *,
    project: str,
    ticket: TicketInput,
    model: str,
    max_tokens: int,
    temperature: float,
) -> Tuple[RefinedTicket, str]:
    messages = build_ticket_refine_messages(
        project=project,
        ticket={
            "issue_key": ticket.issue_key,
            "summary": ticket.summary,
            "description": ticket.description,
        },
    )
    response = chat_completion(messages, model=model, max_tokens=max_tokens, temperature=temperature)
    parsed = _parse_json(response)

    refined_summary = (parsed.get("refined_summary") or "").strip() or (ticket.summary or "").strip()
    refined_description = (parsed.get("refined_description") or "").strip() or (ticket.description or "").strip()
    ac_list = parsed.get("acceptance_criteria") or []
    if not isinstance(ac_list, list) or not ac_list:
        ac_list = ["Not enough information provided"]
    ac_list = [str(item).strip() for item in ac_list if str(item).strip()]
    
    ticket_diagnosis = (parsed.get("ticket_diagnosis") or "").strip() or None
    suggested_epic = (parsed.get("suggested_epic") or "").strip() or None
    suggested_fix_version_group = (parsed.get("suggested_fix_version_group") or "").strip() or None

    return (
        RefinedTicket(
            issue_key=ticket.issue_key,
            refined_summary=refined_summary,
            refined_description=refined_description,
            acceptance_criteria=ac_list,
            parent_key=ticket.parent_key,
            fix_versions=list(ticket.fix_versions),
            ticket_diagnosis=ticket_diagnosis,
            suggested_epic=suggested_epic,
            suggested_fix_version_group=suggested_fix_version_group,
        ),
        response,
    )


