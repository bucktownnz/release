"""File writing utilities."""

import os
from pathlib import Path
from typing import Tuple


def write_outputs(
    out_dir: str,
    fix_version_notes: str,
    confluence_notes: str,
    slack_announcement: str,
) -> Tuple[str, str, str]:
    """
    Write three output files to the output directory.
    
    Args:
        out_dir: Output directory path
        fix_version_notes: Jira Fix Version notes content
        confluence_notes: Confluence notes content
        slack_announcement: Slack announcement content
    
    Returns:
        Tuple of (fix_version_path, confluence_path, slack_path)
    """
    # Ensure output directory exists
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    
    # Write files
    fix_version_path = os.path.join(out_dir, "jira_fix_version_notes.md")
    confluence_path = os.path.join(out_dir, "confluence_release_notes.md")
    slack_path = os.path.join(out_dir, "slack_announcement.txt")
    
    with open(fix_version_path, "w", encoding="utf-8") as f:
        f.write(fix_version_notes)
    
    with open(confluence_path, "w", encoding="utf-8") as f:
        f.write(confluence_notes)
    
    with open(slack_path, "w", encoding="utf-8") as f:
        f.write(slack_announcement)
    
    return fix_version_path, confluence_path, slack_path

