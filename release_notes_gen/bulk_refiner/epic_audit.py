from __future__ import annotations

import json
from collections import defaultdict
from typing import Dict, List, Tuple

from json import JSONDecodeError

from release_notes_gen.llm import chat_completion
from .prompts import build_epic_suggestion_messages
from .types import EpicAudit, EpicSuggestion, RefinedTicket


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

    # First try direct parse
    try:
        return json.loads(stripped)
    except Exception:
        pass

    # Fallback: scan for the first balanced JSON object
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
                    # keep scanning in case there's a later valid object
                    start_index = None

    # As a last resort, re-raise the original error for visibility
    raise json.JSONDecodeError("Could not find valid JSON object in response", stripped, 0)


def run_epic_audit(
    *,
    tickets: List[RefinedTicket],
    model: str,
    max_tokens: int,
    temperature: float,
) -> Tuple[EpicAudit, str]:
    payload = [
        {"issue_key": t.issue_key, "refined_summary": t.refined_summary, "summary": t.refined_summary}
        for t in tickets
    ]
    messages = build_epic_suggestion_messages(tickets=payload)
    response = chat_completion(messages, model=model, max_tokens=max_tokens, temperature=temperature)

    try:
        parsed = _parse_json(response)
        per_ticket_suggestions = parsed.get("per_ticket_suggestions") or {}
        recommended_epics_raw = parsed.get("recommended_epics") or []
        suggested_total_epics = int(parsed.get("suggested_total_epics") or 0)

        recommended_epics: List[EpicSuggestion] = []
        for item in recommended_epics_raw:
            name = (item.get("name") or "").strip()
            reason = (item.get("reason") or "").strip()
            tks = [str(x).strip() for x in (item.get("tickets") or []) if str(x).strip()]
            if name:
                recommended_epics.append(
                    EpicSuggestion(suggested_epic_name=name, reason=reason, tickets=tks)
                )
    except JSONDecodeError:
        # Fallback: simple heuristic audit with no groupings
        per_ticket_suggestions = {}
        recommended_epics = []
        suggested_total_epics = 0

    missing_count = sum(1 for t in tickets if not (t.parent_key or "").strip())
    percent_missing = (missing_count / max(1, len(tickets))) * 100.0

    return (
        EpicAudit(
            percent_missing_epic=percent_missing,
            recommended_epics=recommended_epics,
            suggested_total_epics=max(suggested_total_epics, len(recommended_epics)),
            per_ticket_suggestions={str(k): (v or None) for k, v in per_ticket_suggestions.items()},
        ),
        response,
    )


