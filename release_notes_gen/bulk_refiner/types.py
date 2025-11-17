from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


RequiredColumns = Tuple[str, str, str, str, str]


@dataclass(slots=True)
class TicketInput:
    issue_key: str
    summary: str
    description: str
    parent_key: Optional[str] = None
    fix_versions: List[str] = field(default_factory=list)
    raw: Dict[str, Optional[str]] = field(default_factory=dict)


@dataclass(slots=True)
class RefinedTicket:
    issue_key: str
    refined_summary: str
    refined_description: str
    acceptance_criteria: List[str]
    parent_key: Optional[str] = None
    fix_versions: List[str] = field(default_factory=list)


@dataclass(slots=True)
class EpicSuggestion:
    suggested_epic_name: str
    reason: str
    tickets: List[str] = field(default_factory=list)


@dataclass(slots=True)
class EpicAudit:
    percent_missing_epic: float
    recommended_epics: List[EpicSuggestion]
    suggested_total_epics: int
    per_ticket_suggestions: Dict[str, Optional[str]]  # issue_key -> suggested epic or None


@dataclass(slots=True)
class FixVersionGroup:
    name: str
    tickets: List[str]
    rationale: Optional[str] = None


@dataclass(slots=True)
class FixVersionRecommendation:
    groups: List[FixVersionGroup]


@dataclass(slots=True)
class ProcessingBatchResult:
    refined_tickets: List[RefinedTicket]
    errors: List[str] = field(default_factory=list)


@dataclass(slots=True)
class BulkRefinerResult:
    refined: List[RefinedTicket]
    epic_audit: EpicAudit
    fix_versions: FixVersionRecommendation


