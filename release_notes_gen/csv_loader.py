"""CSV loading and parsing with flexible column detection."""

import csv
import io
from typing import List, Dict, Optional, Tuple


# Column aliases for flexible detection
SUMMARY_ALIASES = ["summary", "issue summary", "title"]
DESCRIPTION_ALIASES = ["description", "issue description", "details"]
KEY_ALIASES = ["key", "issue key"]


def find_column(
    headers: List[str], aliases: List[str], override: Optional[str] = None
) -> Optional[int]:
    """Find column index by name, case-insensitively."""
    if override:
        override_lower = override.lower().strip()
        for i, header in enumerate(headers):
            if header.lower().strip() == override_lower:
                return i
        raise ValueError(f"Override column '{override}' not found in CSV headers")
    
    headers_lower = [h.lower().strip() for h in headers]
    for alias in aliases:
        if alias.lower() in headers_lower:
            return headers_lower.index(alias.lower())
    return None


def load_csv(
    file_path: Optional[str] = None,
    file_content: Optional[bytes] = None,
    summary_col: Optional[str] = None,
    description_col: Optional[str] = None,
    key_col: Optional[str] = None,
    limit: int = 0,
) -> Tuple[List[Dict[str, Optional[str]]], Dict[str, Optional[str]]]:
    """
    Load and parse CSV file.
    
    Args:
        file_path: Path to CSV file (if provided)
        file_content: Raw CSV content as bytes (if provided)
        summary_col: Override for summary column name
        description_col: Override for description column name
        key_col: Override for key column name
        limit: Maximum rows to process (0 = all)
    
    Returns:
        List of dicts with keys: key, summary, description
    """
    if file_path and file_content:
        raise ValueError("Provide either file_path or file_content, not both")
    if not file_path and not file_content:
        raise ValueError("Provide either file_path or file_content")
    
    # Read content
    if file_path:
        # Try UTF-8-sig first, then UTF-8
        try:
            with open(file_path, "r", encoding="utf-8-sig", newline="") as f:
                content = f.read()
        except UnicodeDecodeError:
            with open(file_path, "r", encoding="utf-8", newline="") as f:
                content = f.read()
    else:
        # Try UTF-8-sig first, then UTF-8
        try:
            content = file_content.decode("utf-8-sig")
        except UnicodeDecodeError:
            content = file_content.decode("utf-8")
    
    # Parse CSV
    reader = csv.DictReader(io.StringIO(content))
    headers = reader.fieldnames or []
    
    if not headers:
        raise ValueError("CSV file has no headers")
    
    # Find columns
    summary_idx = find_column(headers, SUMMARY_ALIASES, summary_col)
    description_idx = find_column(headers, DESCRIPTION_ALIASES, description_col)
    key_idx = find_column(headers, KEY_ALIASES, key_col)
    
    if summary_idx is None:
        raise ValueError(
            f"Summary column not found. Available columns: {', '.join(headers)}. "
            f"Expected aliases: {', '.join(SUMMARY_ALIASES)}"
        )
    if description_idx is None:
        raise ValueError(
            f"Description column not found. Available columns: {', '.join(headers)}. "
            f"Expected aliases: {', '.join(DESCRIPTION_ALIASES)}"
        )
    
    summary_col_name = headers[summary_idx]
    description_col_name = headers[description_idx]
    key_col_name = headers[key_idx] if key_idx is not None else None
    
    # Parse rows
    tickets = []
    for i, row in enumerate(reader):
        if limit > 0 and i >= limit:
            break
        
        ticket = {
            "key": row.get(key_col_name, "").strip() if key_col_name else None,
            "summary": row.get(summary_col_name, "").strip(),
            "description": row.get(description_col_name, "").strip(),
        }
        
        # Skip empty rows
        if not ticket["summary"] and not ticket["description"]:
            continue
        
        tickets.append(ticket)
    
    return tickets, {
        "summary": summary_col_name,
        "description": description_col_name,
        "key": key_col_name,
    }

