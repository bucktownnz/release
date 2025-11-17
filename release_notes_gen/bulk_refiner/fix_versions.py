from __future__ import annotations

import json
from typing import Dict, List, Tuple

from release_notes_gen.llm import chat_completion
from .prompts import build_fix_version_grouping_messages
from .types import FixVersionGroup, FixVersionRecommendation, RefinedTicket


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


def suggest_fix_version_groups(
    *,
    tickets: List[RefinedTicket],
    model: str,
    max_tokens: int,
    temperature: float,
) -> Tuple[FixVersionRecommendation, str]:
    payload = [
        {"issue_key": t.issue_key, "refined_summary": t.refined_summary, "summary": t.refined_summary}
        for t in tickets
    ]
    messages = build_fix_version_grouping_messages(tickets=payload)
    response = chat_completion(messages, model=model, max_tokens=max_tokens, temperature=temperature)
    parsed = _parse_json(response)

    groups_raw = parsed.get("groups") or []
    groups: List[FixVersionGroup] = []
    for g in groups_raw:
        name = (g.get("name") or "").strip()
        tks = [str(x).strip() for x in (g.get("tickets") or []) if str(x).strip()]
        rationale = (g.get("rationale") or "").strip() or None
        if name and tks:
            groups.append(FixVersionGroup(name=name, tickets=tks, rationale=rationale))

    return FixVersionRecommendation(groups=groups), response


