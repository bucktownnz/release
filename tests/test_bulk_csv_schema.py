from __future__ import annotations

from release_notes_gen.bulk_refiner.csv_schema import load_bulk_csv


def test_load_bulk_csv_minimal_valid():
    csv_bytes = (
        "Issue Key,Summary,Description,Parent Key,Fix Versions\n"
        "CUS-1,Do thing,Some description,,v1.0\n"
        "CUS-2,Do other,More description,EPIC-1,\"v1.0, v1.1\"\n"
    ).encode("utf-8")

    tickets, detected = load_bulk_csv(csv_bytes)
    assert len(tickets) == 2
    assert detected["Issue Key"] == "Issue Key"
    assert tickets[0].issue_key == "CUS-1"
    assert tickets[0].fix_versions == ["v1.0"]
    assert tickets[1].parent_key == "EPIC-1"
    assert tickets[1].fix_versions == ["v1.0", "v1.1"]


def test_load_bulk_csv_missing_columns():
    csv_bytes = (
        "Issue Key,Summary,Parent Key,Fix Versions\n"
        "CUS-1,Do thing,,v1.0\n"
    ).encode("utf-8")
    try:
        load_bulk_csv(csv_bytes)
        assert False, "Expected ValueError for missing Description column"
    except ValueError as exc:
        assert "Missing required columns" in str(exc)


