"""Epic Pack refinement pipeline orchestrating parsing, LLM calls, and outputs."""

from __future__ import annotations

import json
import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from release_notes_gen.llm import chat_completion
from release_notes_gen.profiles.squads import (
    format_squad_context,
    load_squad_profile,
)

from .parse import ParseResult, TicketRow, parse_epic_csv, EpicValidationError
from .prompts import (
    build_epic_messages,
    build_gap_analysis_messages,
    build_missing_tickets_messages,
    build_ticket_messages,
)
from .writer import write_epic_pack


PROMPT_VERSION = "2024-11-epic-pack-v1"
DEFAULT_TRUNCATION = 0
WEASEL_WORDS = ("etc", "tbd", "asap")


def _hash_dict(payload: Dict[str, Any]) -> str:
    payload_json = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
    return digest


def _hash_text(text: Optional[str]) -> str:
    if not text:
        return "none"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalise_json(text: str) -> str:
    """Strip optional fenced code blocks from responses."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return stripped


def _parse_json_response(response: str) -> Dict[str, Any]:
    normalised = _normalise_json(response)
    return json.loads(normalised)


def _truncate_text(text: str, limit: int) -> Tuple[str, bool]:
    if limit is None or limit <= 0:
        return text, False
    if len(text) <= limit:
        return text, False
    truncated = text[:limit].rstrip()
    note = f"\n\n[Description truncated after {limit} characters]"
    return f"{truncated}{note}", True


def _contains_weasel_word(value: str) -> bool:
    lower_value = value.lower()
    return any(word in lower_value for word in WEASEL_WORDS)


def lint_ticket_output(output: Dict[str, Any]) -> List[str]:
    """Validate ticket output and return list of issues."""
    issues: List[str] = []

    title = output.get("title", "") or ""
    summary = output.get("summary", "") or ""
    ac_list = output.get("acceptance_criteria")

    if not title.strip():
        issues.append("Missing title")
    if _contains_weasel_word(title):
        issues.append("Title contains weasel words")

    if not summary.strip():
        issues.append("Missing summary")
    if len(summary) > 500:
        issues.append("Summary exceeds 500 characters")
    if _contains_weasel_word(summary):
        issues.append("Summary contains weasel words")

    if not isinstance(ac_list, list) or not ac_list:
        issues.append("Acceptance criteria missing or empty")
    else:
        for idx, ac in enumerate(ac_list, start=1):
            if not all(ac.get(field, "").strip() for field in ("given", "when", "then")):
                issues.append(f"Acceptance criterion {idx} missing Given/When/Then")
            for field in ("given", "when", "then"):
                value = ac.get(field, "")
                if _contains_weasel_word(value):
                    issues.append(f"Acceptance criterion {idx} uses weasel words")

    for list_key in ("risks", "test_ideas"):
        value = output.get(list_key)
        if not isinstance(value, list):
            issues.append(f"{list_key} must be a list")

    questions = output.get("questions")
    if questions is not None and not isinstance(questions, list):
        issues.append("Questions must be a list when present")

    return issues


class JsonCache:
    """Simple file-based JSON cache keyed by content hash."""

    def __init__(self, cache_dir: str):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        path = self._path(key)
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError):
            return None

    def set(self, key: str, value: Dict[str, Any]) -> None:
        path = self._path(key)
        tmp_path = path.with_suffix(".json.tmp")
        with self._lock:
            with tmp_path.open("w", encoding="utf-8") as fh:
                json.dump(value, fh, ensure_ascii=False, indent=2)
            tmp_path.replace(path)


@dataclass(slots=True)
class TicketRefineResult:
    ticket: TicketRow
    output: Dict[str, Any]
    raw_response: str
    lint_feedback: List[str] = field(default_factory=list)
    truncated_description: bool = False


@dataclass(slots=True)
class EpicRefineResult:
    epic: TicketRow
    output: Dict[str, Any]
    raw_response: str


@dataclass(slots=True)
class MissingTicketSuggestions:
    suggested_tickets: List[Dict[str, Any]]
    raw_response: str


@dataclass(slots=True)
class GapAnalysisResult:
    actions_by_ticket: Dict[str, List[str]]
    themes: List[str]
    raw_response: str


@dataclass(slots=True)
class EpicPackOutputs:
    output_directory: str
    epic_md: str
    stories_md: str
    actions_md: str
    suggestions_md: str
    index_md: str
    refined_csv: str
    zip_path: str


@dataclass(slots=True)
class EpicPackConfig:
    project: str
    model: str = "gpt-4o-mini"
    temperature: float = 0.0
    max_tokens: int = 1800
    concurrency: int = 3
    output_base_dir: str = "./out/epic_packs"
    ticket_example: Optional[str] = None
    epic_example: Optional[str] = None
    cache_dir: str = "./out/.epic_refiner_cache"
    dry_run: bool = False
    truncation_chars: int = DEFAULT_TRUNCATION
    prompt_version: str = PROMPT_VERSION

    def __post_init__(self) -> None:
        if self.concurrency < 1:
            self.concurrency = 1
        if self.truncation_chars is not None and self.truncation_chars < 0:
            self.truncation_chars = 0


@dataclass(slots=True)
class EpicPackResult:
    parse_result: ParseResult
    ticket_results: List[TicketRefineResult]
    epic_result: Optional[EpicRefineResult]
    gap_analysis: Optional[GapAnalysisResult]
    suggestions: Optional[MissingTicketSuggestions]
    outputs: Optional[EpicPackOutputs]
    cache_hits: Dict[str, int]
    ticket_errors: List[str] = field(default_factory=list)


class LLMResponseError(RuntimeError):
    """Raised when LLM output cannot be parsed or validated."""


def _invoke_json_model(
    base_messages: List[Dict[str, str]],
    *,
    model: str,
    max_tokens: int,
    temperature: float,
    lint_callback: Optional[Any] = None,
    allow_retry: bool = True,
) -> Tuple[Dict[str, Any], str, List[str]]:
    """Invoke model ensuring JSON-only responses and lint correction."""

    messages = list(base_messages)
    lint_feedback: List[str] = []

    for attempt in range(2 if allow_retry else 1):
        response_text = chat_completion(
            messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        try:
            parsed = _parse_json_response(response_text)
        except json.JSONDecodeError as exc:
            lint_feedback.append(f"Invalid JSON response: {exc}")
            if attempt == 0 and allow_retry:
                messages = list(base_messages) + [
                    {
                        "role": "user",
                        "content": (
                            "The previous response was not valid JSON. "
                            "Please respond with valid JSON only, following the required schema."
                        ),
                    }
                ]
                continue
            raise LLMResponseError("Failed to parse JSON response") from exc

        if lint_callback:
            lint_issues = lint_callback(parsed)
            if lint_issues:
                lint_feedback.extend(lint_issues)
                if attempt == 0 and allow_retry:
                    human_issues = "\n".join(f"- {issue}" for issue in lint_issues)
                    messages = list(base_messages) + [
                        {
                            "role": "user",
                            "content": (
                                "The previous JSON output failed validation for the following reasons:\n"
                                f"{human_issues}\n"
                                "Please correct these issues and resend the full JSON response. "
                                "Remember to avoid weasel words and ensure each acceptance criterion includes Given/When/Then."
                            ),
                        }
                    ]
                    continue
                raise LLMResponseError(
                    f"LLM output failed validation: {', '.join(lint_issues)}"
                )

        return parsed, response_text, lint_feedback

    raise LLMResponseError("Exceeded retry attempts for JSON response")


def _build_ticket_payload(ticket: TicketRow, truncation: int) -> Tuple[Dict[str, Any], bool]:
    description, truncated = _truncate_text(ticket.description or "", truncation)
    if truncated:
        description = f"{description}\n\n[Description truncated after {truncation} characters]"

    payload = {
        "key": ticket.key,
        "issue_type": ticket.issue_type,
        "summary": ticket.summary,
        "description": description,
        "status": ticket.status,
        "labels": ticket.labels,
        "story_points": ticket.story_points,
        "priority": ticket.priority,
        "assignee": ticket.assignee,
        "created": ticket.created,
        "updated": ticket.updated,
    }
    return payload, truncated


def _build_epic_payload(epic: TicketRow, truncation: int) -> Dict[str, Any]:
    description, truncated = _truncate_text(epic.description or "", truncation)
    if truncated:
        description = f"{description}\n\n[Description truncated after {truncation} characters]"

    return {
        "key": epic.key,
        "issue_type": epic.issue_type,
        "summary": epic.summary,
        "description": description,
        "status": epic.status,
        "labels": epic.labels,
        "assignee": epic.assignee,
        "created": epic.created,
        "updated": epic.updated,
    }


def _child_summaries_for_epic(ticket_results: List[TicketRefineResult]) -> List[Dict[str, Any]]:
    summaries = []
    for result in ticket_results:
        summaries.append(
            {
                "key": result.ticket.key,
                "refined_title": result.output.get("title"),
                "refined_summary": result.output.get("summary"),
                "issue_type": result.ticket.issue_type,
            }
        )
    return summaries


def run_epic_pack_pipeline(
    *,
    file_path: Optional[str] = None,
    file_content: Optional[bytes] = None,
    column_overrides: Optional[Dict[str, str]] = None,
    config: EpicPackConfig,
    progress_callback: Optional[Callable[[str], None]] = None,
    squad: Optional[str] = None,
) -> EpicPackResult:
    """Execute the full epic pack refinement pipeline."""
    def _emit(message: str) -> None:
        if progress_callback:
            try:
                progress_callback(message)
            except Exception:
                pass

    _emit("Parsing CSV input...")
    parse_result = parse_epic_csv(
        file_path=file_path,
        file_content=file_content,
        column_overrides=column_overrides,
    )
    _emit(
        f"Parse complete: epic {parse_result.epic.key} with {len(parse_result.children)} child tickets."
    )

    cache = JsonCache(config.cache_dir)
    cache_hits = {"tickets": 0, "epic": 0, "suggestions": 0, "gap": 0}

    squad_context: Optional[str] = None
    if squad:
        profile = load_squad_profile(squad)
        if profile:
            squad_context = format_squad_context(profile)
            display = profile.get("display_name") or squad
            _emit(f"Loaded squad context for {display}.")
        else:
            _emit(f"Warning: squad '{squad}' not found. Continuing without squad context.")

    if config.dry_run:
        return EpicPackResult(
            parse_result=parse_result,
            ticket_results=[],
            epic_result=None,
            gap_analysis=None,
            suggestions=None,
            outputs=None,
            cache_hits=cache_hits,
        )

    epic_title_seed = parse_result.epic.summary or parse_result.epic.key

    def process_ticket(ticket: TicketRow) -> TicketRefineResult:
        payload, truncated = _build_ticket_payload(ticket, config.truncation_chars)
        cache_payload = {
            "version": config.prompt_version,
            "model": config.model,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "project": config.project,
            "epic_title": epic_title_seed,
            "ticket": payload,
            "example_hash": _hash_text(config.ticket_example),
            "squad_context": _hash_text(squad_context),
        }
        cache_key = _hash_dict(cache_payload)

        cached = cache.get(cache_key)
        if cached:
            cache_hits["tickets"] += 1
            return TicketRefineResult(
                ticket=ticket,
                output=cached["output"],
                raw_response=cached["raw_response"],
                lint_feedback=cached.get("lint_feedback", []),
                truncated_description=truncated,
            )

        messages = build_ticket_messages(
            project=config.project,
            epic_title=epic_title_seed,
            ticket_payload=payload,
            example_format=config.ticket_example,
            squad_context=squad_context,
        )

        parsed, raw_response, lint_feedback = _invoke_json_model(
            messages,
            model=config.model,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
            lint_callback=lint_ticket_output,
        )

        cache.set(
            cache_key,
            {
                "output": parsed,
                "raw_response": raw_response,
                "lint_feedback": lint_feedback,
            },
        )

        return TicketRefineResult(
            ticket=ticket,
            output=parsed,
            raw_response=raw_response,
            lint_feedback=lint_feedback,
            truncated_description=truncated,
        )

    ticket_errors: List[str] = []

    with ThreadPoolExecutor(max_workers=config.concurrency) as executor:
        futures = {executor.submit(process_ticket, ticket): ticket for ticket in parse_result.children}
        ticket_results: List[TicketRefineResult] = []
        for future in as_completed(futures):
            ticket = futures[future]
            try:
                ticket_results.append(future.result())
            except Exception as exc:  # pragma: no cover - defensive guard
                ticket_identifier = ticket.key or f"(row {ticket.row_number})"
                error_msg = f"{ticket_identifier} refinement failed: {exc}"
                ticket_errors.append(error_msg)
                _emit(f"Ticket {ticket_identifier} failed: {exc}")
    if not ticket_results:
        raise LLMResponseError("All ticket refinements failed; aborting epic run.")
    ticket_results.sort(key=lambda result: result.ticket.row_number)
    _emit(f"Refined {len(ticket_results)} child tickets.")

    # Epic refinement
    epic_payload = _build_epic_payload(parse_result.epic, config.truncation_chars)
    child_summaries = _child_summaries_for_epic(ticket_results)

    epic_cache_payload = {
        "version": config.prompt_version,
        "model": config.model,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "project": config.project,
        "epic": epic_payload,
        "children": child_summaries,
        "example_hash": _hash_text(config.epic_example),
        "squad_context": _hash_text(squad_context),
    }
    epic_cache_key = _hash_dict(epic_cache_payload)
    cached_epic = cache.get(epic_cache_key)

    if cached_epic:
        cache_hits["epic"] += 1
        epic_result = EpicRefineResult(
            epic=parse_result.epic,
            output=cached_epic["output"],
            raw_response=cached_epic["raw_response"],
        )
    else:
        epic_messages = build_epic_messages(
            project=config.project,
            epic_payload=epic_payload,
            child_ticket_summaries=child_summaries,
            example_format=config.epic_example,
            squad_context=squad_context,
        )
        parsed_epic, epic_raw, _ = _invoke_json_model(
            epic_messages,
            model=config.model,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
            lint_callback=None,
        )
        cache.set(
            epic_cache_key,
            {
                "output": parsed_epic,
                "raw_response": epic_raw,
            },
        )
        epic_result = EpicRefineResult(
            epic=parse_result.epic,
            output=parsed_epic,
            raw_response=epic_raw,
        )
    _emit("Epic refinement complete.")

    # Missing ticket suggestions
    suggestion_cache_payload = {
        "version": config.prompt_version,
        "model": config.model,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "epic_narrative": epic_result.output.get("narrative", ""),
        "children": child_summaries,
        "squad_context": _hash_text(squad_context),
    }
    suggestion_key = _hash_dict(suggestion_cache_payload)
    cached_suggestions = cache.get(suggestion_key)
    if cached_suggestions:
        cache_hits["suggestions"] += 1
        suggestions = MissingTicketSuggestions(
            suggested_tickets=cached_suggestions["suggested_tickets"],
            raw_response=cached_suggestions["raw_response"],
        )
    else:
        suggestions_messages = build_missing_tickets_messages(
            epic_narrative=epic_result.output.get("narrative", ""),
            child_ticket_summaries=child_summaries,
            squad_context=squad_context,
        )
        parsed_suggestions, suggestions_raw, _ = _invoke_json_model(
            suggestions_messages,
            model=config.model,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
            lint_callback=None,
        )
        suggestions = MissingTicketSuggestions(
            suggested_tickets=parsed_suggestions.get("suggested_tickets", []),
            raw_response=suggestions_raw,
        )
        cache.set(
            suggestion_key,
            {
                "suggested_tickets": suggestions.suggested_tickets,
                "raw_response": suggestions_raw,
            },
        )
    _emit("Ambition and missing ticket suggestions complete.")

    # Gap analysis
    gap_payload_data = [
        {
            "key": result.ticket.key,
            "questions": result.output.get("questions") or [],
        }
        for result in ticket_results
        if result.output.get("questions")
    ]
    gap_cache_payload = {
        "version": config.prompt_version,
        "model": config.model,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "tickets": gap_payload_data,
        "squad_context": _hash_text(squad_context),
    }
    gap_cache_key = _hash_dict(gap_cache_payload)
    cached_gap = cache.get(gap_cache_key)

    if cached_gap:
        cache_hits["gap"] += 1
        gap_analysis = GapAnalysisResult(
            actions_by_ticket=cached_gap["actions_by_ticket"],
            themes=cached_gap.get("themes", []),
            raw_response=cached_gap["raw_response"],
        )
    else:
        gap_messages = build_gap_analysis_messages(
            ticket_results=gap_payload_data,
            squad_context=squad_context,
        )
        parsed_gap, gap_raw, _ = _invoke_json_model(
            gap_messages,
            model=config.model,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
            lint_callback=None,
            allow_retry=False,
        )
        gap_analysis = GapAnalysisResult(
            actions_by_ticket=parsed_gap.get("actions_by_ticket", {}),
            themes=parsed_gap.get("themes", []),
            raw_response=gap_raw,
        )
        cache.set(
            gap_cache_key,
            {
                "actions_by_ticket": gap_analysis.actions_by_ticket,
                "themes": gap_analysis.themes,
                "raw_response": gap_raw,
            },
        )
    _emit("Gap analysis complete.")

    # Write outputs
    outputs = write_epic_pack(
        output_base_dir=config.output_base_dir,
        parse_result=parse_result,
        ticket_results=ticket_results,
        epic_result=epic_result,
        suggestions=suggestions,
        gap_analysis=gap_analysis,
        cache_hits=cache_hits,
        ticket_errors=ticket_errors,
    )
    _emit(f"Outputs written to {outputs.output_directory}.")

    return EpicPackResult(
        parse_result=parse_result,
        ticket_results=ticket_results,
        epic_result=epic_result,
        gap_analysis=gap_analysis,
        suggestions=suggestions,
        outputs=outputs,
        cache_hits=cache_hits,
        ticket_errors=ticket_errors,
    )

