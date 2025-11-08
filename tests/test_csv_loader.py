import pytest

from release_notes_gen.csv_loader import load_csv


def test_load_csv_detects_aliases():
    csv_data = "Key,Issue Summary,Issue Description\nCPS-123,Add feature,Implements feature details\n"
    tickets, columns = load_csv(file_content=csv_data.encode("utf-8"))

    assert columns["summary"] == "Issue Summary"
    assert columns["description"] == "Issue Description"
    assert columns["key"] == "Key"

    assert len(tickets) == 1
    assert tickets[0]["summary"] == "Add feature"
    assert tickets[0]["description"] == "Implements feature details"
    assert tickets[0]["key"] == "CPS-123"


def test_load_csv_handles_utf8_bom():
    csv_data = "\ufeffKey,Summary,Description\nCPS-1,Title,Details\n"
    tickets, columns = load_csv(file_content=csv_data.encode("utf-8"))

    assert columns["summary"] == "Summary"
    assert columns["description"] == "Description"
    assert tickets[0]["summary"] == "Title"


def test_load_csv_with_overrides_and_limit():
    csv_data = "Ticket,SummaryText,Details\nCPS-1,Title1,Detail1\nCPS-2,Title2,Detail2\n"
    tickets, columns = load_csv(
        file_content=csv_data.encode("utf-8"),
        summary_col="SummaryText",
        description_col="Details",
        key_col="Ticket",
        limit=1,
    )

    assert columns == {
        "summary": "SummaryText",
        "description": "Details",
        "key": "Ticket",
    }
    assert len(tickets) == 1
    assert tickets[0]["summary"] == "Title1"


def test_load_csv_missing_summary_column_raises():
    csv_data = "Key,Subject,Description\nCPS-1,Title,Desc\n"
    with pytest.raises(ValueError) as exc:
        load_csv(file_content=csv_data.encode("utf-8"))

    assert "Summary column not found" in str(exc.value)
