from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from .csv_schema import load_bulk_csv
from .epic_audit import run_epic_audit
from .fix_versions import suggest_fix_version_groups
from .refine import refine_ticket
from .types import (
    BulkRefinerResult,
    ProcessingBatchResult,
    RefinedTicket,
    TicketInput,
)


@dataclass(slots=True)
class BulkRefinerConfig:
    project: str
    model: str = "gpt-4o-mini"
    max_tokens: int = 1600
    temperature: float = 0.2
    batch_size: int = 50


def process_batch(
    *,
    project: str,
    tickets: List[TicketInput],
    model: str,
    max_tokens: int,
    temperature: float,
    progress: Optional[Callable[[str], None]] = None,
) -> ProcessingBatchResult:
    refined: List[RefinedTicket] = []
    errors: List[str] = []
    for idx, ticket in enumerate(tickets, start=1):
        try:
            result, _ = refine_ticket(
                project=project,
                ticket=ticket,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            refined.append(result)
            if progress:
                progress(f"Refined {ticket.issue_key} ({idx}/{len(tickets)})")
        except Exception as exc:
            errors.append(f"{ticket.issue_key or '(no key)'}: {exc}")
    return ProcessingBatchResult(refined_tickets=refined, errors=errors)


def run_bulk_refiner_pipeline(
    *,
    file_bytes: bytes,
    config: BulkRefinerConfig,
    progress: Optional[Callable[[str], None]] = None,
) -> Tuple[BulkRefinerResult, Dict[str, str], List[str]]:
    """
    Execute the Bulk Ticket Refiner pipeline.

    Returns:
        (result, detected_columns, errors)
    """
    def emit(msg: str) -> None:
        if progress:
            try:
                progress(msg)
            except Exception:
                pass

    emit("Parsing CSV...")
    tickets, detected = load_bulk_csv(file_bytes)
    emit(f"Loaded {len(tickets)} tickets.")

    # Batch refinement
    refined_all: List[RefinedTicket] = []
    errors_all: List[str] = []

    if not tickets:
        raise ValueError("CSV contained no valid ticket rows.")

    for start in range(0, len(tickets), config.batch_size):
        end = min(start + config.batch_size, len(tickets))
        batch = tickets[start:end]
        emit(f"Processing batch {start//config.batch_size + 1}: {len(batch)} tickets...")
        batch_result = process_batch(
            project=config.project,
            tickets=batch,
            model=config.model,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
            progress=progress,
        )
        refined_all.extend(batch_result.refined_tickets)
        errors_all.extend(batch_result.errors)

    # Epic Audit
    emit("Running epic audit...")
    epic_audit, _ = run_epic_audit(
        tickets=refined_all,
        model=config.model,
        max_tokens=config.max_tokens,
        temperature=config.temperature,
    )

    # Fix Version Grouping
    emit("Suggesting fix version groups...")
    fix_versions, _ = suggest_fix_version_groups(
        tickets=refined_all,
        model=config.model,
        max_tokens=config.max_tokens,
        temperature=config.temperature,
    )

    return (
        BulkRefinerResult(
            refined=refined_all,
            epic_audit=epic_audit,
            fix_versions=fix_versions,
        ),
        detected,
        errors_all,
    )


