import pytest

from release_notes_gen.epic_refiner.parse import EpicValidationError, parse_epic_csv


def _csv_bytes(text: str) -> bytes:
    return text.strip().encode("utf-8")


def test_parse_epic_csv_success() -> None:
    csv_text = """
Issue key,Issue Type,Summary,Description,Parent key
EPIC-123,Epic,Improve onboarding,As a PM I want..., 
STORY-1,Story,First slice,Implement flow,EPIC-123
BUG-2,Bug,Fix regression,Fix bug,EPIC-123
"""
    result = parse_epic_csv(file_content=_csv_bytes(csv_text))

    assert result.epic.key == "EPIC-123"
    assert len(result.children) == 2
    assert not result.warnings
    assert not result.excluded_rows


def test_parse_epic_csv_excludes_invalid_parent() -> None:
    csv_text = """
Issue key,Issue Type,Summary,Description,Parent key
EPIC-1,Epic,Refactor billing,Long description,
TASK-1,Task,Adjust invoices,Some text,EPIC-1
TASK-2,Task,Wrong parent,Should be excluded,OTHER-999
"""
    result = parse_epic_csv(file_content=_csv_bytes(csv_text))

    assert len(result.children) == 1
    assert len(result.excluded_rows) == 1
    excluded = result.excluded_rows[0]
    assert excluded.key == "TASK-2"
    assert "does not match epic" in excluded.reason.lower()


def test_parse_epic_csv_requires_epic() -> None:
    csv_text = """
Issue key,Issue Type,Summary,Description,Parent key
TASK-1,Task,Adjust invoices,Some text,EPIC-1
"""
    with pytest.raises(EpicValidationError):
        parse_epic_csv(file_content=_csv_bytes(csv_text))


