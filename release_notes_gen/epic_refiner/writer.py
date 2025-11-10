"""Output writer for Epic Pack Refiner artefacts."""

from __future__ import annotations

import csv
import textwrap
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, TYPE_CHECKING

from .parse import ParseResult

if TYPE_CHECKING:
    from .pipeline import (
        EpicPackOutputs,
        EpicRefineResult,
        GapAnalysisResult,
        MissingTicketSuggestions,
        TicketRefineResult,
    )


TRACEABILITY_HEADING = "## Traceability"


def _safe_key(value: Optional[str]) -> str:
    return (value or "unknown").strip().replace(" ", "_")


def _format_acceptance_criteria(criteria: Iterable[Dict[str, str]]) -> str:
    lines: List[str] = []
    for item in criteria or []:
        given = item.get("given", "").strip()
        when = item.get("when", "").strip()
        then = item.get("then", "").strip()
        if not any([given, when, then]):
            continue
        lines.append(f"- **Given** {given}\n  **When** {when}\n  **Then** {then}")
    return "\n".join(lines) if lines else "_No acceptance criteria provided._"


def _format_list(values: Optional[Iterable[str]], empty_message: str) -> str:
    items = [v.strip() for v in values or [] if v and v.strip()]
    if not items:
        return empty_message
    return "\n".join(f"- {item}" for item in items)


def _format_ticket_section(result: "TicketRefineResult") -> str:
    output = result.output
    title = output.get("title") or result.ticket.summary or "Untitled ticket"
    section_lines = [
        f"### {result.ticket.key} · {title}",
        "",
        f"**Issue type:** {result.ticket.issue_type or 'Unknown'}",
        "",
        "**Summary**",
        textwrap.fill(output.get("summary", "").strip(), width=90),
        "",
        "**Acceptance criteria**",
        _format_acceptance_criteria(output.get("acceptance_criteria") or []),
        "",
        "**Risks**",
        _format_list(output.get("risks"), "_No risks identified._"),
        "",
        "**Test ideas**",
        _format_list(output.get("test_ideas"), "_No test ideas provided._"),
    ]

    questions = output.get("questions") or []
    if questions:
        section_lines.extend(
            [
                "",
                "**Questions**",
                _format_list(questions, "_No questions raised._"),
            ]
        )

    if result.truncated_description:
        section_lines.extend(
            [
                "",
                "> _Original description truncated for prompting due to length._",
            ]
        )

    if result.lint_feedback:
        section_lines.extend(
            [
                "",
                "> _Model output required correction:_",
                _format_list(result.lint_feedback, ""),
            ]
        )

    return "\n".join(part for part in section_lines if part is not None)


def _build_epic_markdown(epic_result: "EpicRefineResult") -> str:
    output = epic_result.output
    ac_section = _format_acceptance_criteria(output.get("epic_acceptance_criteria") or [])

    parts = [
        f"# {output.get('epic_title') or epic_result.epic.summary or epic_result.epic.key}",
        "",
        "## Narrative",
        textwrap.fill(output.get("narrative", "").strip(), width=100),
        "",
        "## Outcome",
        textwrap.fill(output.get("outcome", "").strip(), width=100),
        "",
        "## Acceptance criteria",
        ac_section,
        "",
        "## Risks",
        _format_list(output.get("risks"), "_No risks highlighted._"),
        "",
        "## Constraints / NFRs",
        _format_list(output.get("constraints_or_nfrs"), "_None stated._"),
        "",
        "## Ambition assessment",
        textwrap.fill(output.get("ambition_assessment", "").strip(), width=100),
    ]

    return "\n".join(parts)


def _build_stories_markdown(ticket_results: List["TicketRefineResult"]) -> str:
    sections = ["# Refined Tickets", ""]
    for result in ticket_results:
        sections.append(_format_ticket_section(result))
        sections.append("")
    return "\n".join(sections).strip() + "\n"


def _build_actions_markdown(
    gap_analysis: Optional["GapAnalysisResult"],
    ticket_results: List["TicketRefineResult"],
) -> str:
    parts = ["# Actions and Open Questions", ""]

    fallback_actions: Dict[str, List[str]] = {}
    for result in ticket_results:
        questions = result.output.get("questions") or []
        if questions:
            fallback_actions[result.ticket.key] = questions

    actions_map = gap_analysis.actions_by_ticket if gap_analysis else fallback_actions
    themes = gap_analysis.themes if gap_analysis else []

    if not actions_map:
        parts.append("_No outstanding questions identified._")
    else:
        for key in sorted(actions_map):
            parts.extend(
                [
                    f"## {key}",
                    _format_list(actions_map[key], "_No actions recorded._"),
                    "",
                ]
            )

    if themes:
        parts.extend(
            [
                "## Shared themes",
                _format_list(themes, "_No shared themes._"),
            ]
        )

    return "\n".join(parts).strip() + "\n"


def _build_suggestions_markdown(
    suggestions: Optional["MissingTicketSuggestions"],
) -> str:
    parts = ["# Suggested New Tickets", ""]
    if not suggestions or not suggestions.suggested_tickets:
        parts.append("_No additional tickets suggested._")
        return "\n".join(parts).strip() + "\n"

    for idx, suggestion in enumerate(suggestions.suggested_tickets, start=1):
        ac_lines = _format_acceptance_criteria(suggestion.get("acceptance_criteria") or [])
        parts.extend(
            [
                f"## {idx}. {suggestion.get('title', 'Untitled')}",
                "",
                "**Outcome**",
                suggestion.get("outcome", "").strip() or "_Outcome not provided._",
                "",
                "**Acceptance criteria**",
                ac_lines,
                "",
            ]
        )
    return "\n".join(parts).strip() + "\n"


def _build_index_markdown(
    parse_result: ParseResult,
    ticket_results: List["TicketRefineResult"],
    ticket_errors: List[str],
    output_dir: Path,
    cache_hits: Dict[str, int],
    run_ts: datetime,
) -> str:
    epic = parse_result.epic
    child_keys = [ticket.ticket.key or "(unknown)" for ticket in ticket_results]
    warnings = parse_result.warnings
    excluded_rows = parse_result.excluded_rows

    parts = [
        "# Epic Pack Summary",
        "",
        f"- **Epic:** {epic.key} · {epic.summary or '(no summary)'}",
        f"- **Children refined:** {len(ticket_results)}",
        f"- **Excluded rows:** {len(excluded_rows)}",
        f"- **Warnings:** {len(warnings)}",
        f"- **Ticket errors:** {len(ticket_errors)}",
        "",
        "## Stats",
        f"- Total CSV rows: {parse_result.stats.get('total_rows', 0)}",
        f"- Epic row number: {parse_result.stats.get('epic_row_number', 'N/A')}",
        f"- Cache hits: tickets {cache_hits.get('tickets', 0)}, epic {cache_hits.get('epic', 0)}, "
        f"suggestions {cache_hits.get('suggestions', 0)}, gap {cache_hits.get('gap', 0)}",
        "",
    ]

    if excluded_rows:
        parts.append("## Excluded rows")
        for excluded in excluded_rows:
            parts.append(
                f"- Row {excluded.row_number}: {excluded.key or '(no key)'} "
                f"({excluded.issue_type or 'Unknown'}) – {excluded.reason}"
            )
        parts.append("")

    if warnings:
        parts.append("## Warnings")
        parts.extend(f"- {warning}" for warning in warnings)
        parts.append("")

    if ticket_errors:
        parts.append("## Ticket refinement errors")
        parts.extend(f"- {error}" for error in ticket_errors)
        parts.append("")

    parts.extend(
        [
            TRACEABILITY_HEADING,
            f"- Output directory: `{output_dir}`",
            f"- Generated: {run_ts.isoformat(timespec='seconds')}",
            f"- Child tickets: {', '.join(child_keys) if child_keys else 'None'}",
        ]
    )

    return "\n".join(parts).strip() + "\n"


def _write_refined_csv(
    destination: Path,
    ticket_results: List[TicketRefineResult],
) -> None:
    with destination.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["Issue key", "Refined Title", "Refined Summary"])
        for result in ticket_results:
            writer.writerow(
                [
                    result.ticket.key,
                    result.output.get("title", ""),
                    result.output.get("summary", ""),
                ]
            )


def _build_zip_archive(folder: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in folder.rglob("*"):
            if file_path.is_file() and file_path != zip_path:
                archive.write(file_path, arcname=file_path.relative_to(folder))


def write_epic_pack(
    *,
    output_base_dir: str,
    parse_result: ParseResult,
    ticket_results: List[TicketRefineResult],
    epic_result: EpicRefineResult,
    suggestions: "MissingTicketSuggestions",
    gap_analysis: "GapAnalysisResult",
    cache_hits: Dict[str, int],
    ticket_errors: List[str],
) -> "EpicPackOutputs":
    """
    Write epic pack artefacts to disk and return metadata.
    """
    run_ts = datetime.now()
    epic_key = _safe_key(parse_result.epic.key)
    timestamp = run_ts.strftime("%Y%m%d_%H%M%S")

    base_dir = Path(output_base_dir).expanduser()
    base_dir.mkdir(parents=True, exist_ok=True)

    output_dir = base_dir / f"{epic_key}_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    epic_md = _build_epic_markdown(epic_result)
    stories_md = _build_stories_markdown(ticket_results)
    actions_md = _build_actions_markdown(gap_analysis, ticket_results)
    suggestions_md = _build_suggestions_markdown(suggestions)
    index_md = _build_index_markdown(
        parse_result=parse_result,
        ticket_results=ticket_results,
        ticket_errors=ticket_errors,
        output_dir=output_dir,
        cache_hits=cache_hits,
        run_ts=run_ts,
    )

    (output_dir / "epic.md").write_text(epic_md, encoding="utf-8")
    (output_dir / "stories.md").write_text(stories_md, encoding="utf-8")
    (output_dir / "actions.md").write_text(actions_md, encoding="utf-8")
    (output_dir / "suggested_new_tickets.md").write_text(suggestions_md, encoding="utf-8")
    (output_dir / "index.md").write_text(index_md, encoding="utf-8")

    csv_path = output_dir / "refined_tickets.csv"
    _write_refined_csv(csv_path, ticket_results)

    zip_path = output_dir / "pack.zip"
    _build_zip_archive(output_dir, zip_path)

    from .pipeline import EpicPackOutputs

    return EpicPackOutputs(
        output_directory=str(output_dir),
        epic_md=epic_md,
        stories_md=stories_md,
        actions_md=actions_md,
        suggestions_md=suggestions_md,
        index_md=index_md,
        refined_csv=str(csv_path),
        zip_path=str(zip_path),
    )


