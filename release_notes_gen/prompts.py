"""Prompt templates for different release note formats."""

from typing import Optional


JIRA_FIX_VERSION_PROMPT = """
You are a Release Manager creating formal Fix Version release notes for Jira.

Generate comprehensive release notes in the following structured format:

# {project} – Fix Version {fix_version} – Release Notes

## Summary
1–2 sentences summarising the overall purpose and impact of this release.

## Release Details
- **Scheduled Release:** {{release_date}} at {{release_time}}  
- **Runbook:** [View Runbook]({{runbook_link}})  
- **Change Request (CR):** [View CR]({{cr_link}})  
- **QA Test Sign-off:** [View QA Results]({{qa_link}})  
- **Release Lead:** {{release_lead}}  
- **Developers Involved:** {{developer_names}}

## Tickets Included
List all tickets included in this release:
- {{key}} – {{summary}}  
  - Brief purpose or value of this change.

## Fix Version Description (Jira Field)
3–5 sentences providing a clear, user-friendly summary of what this release delivers, highlighting business or customer benefits rather than technical details.

If an EXAMPLE FORMAT is provided, match its structure and headings exactly; otherwise, use the default template above.
"""


CONFLUENCE_PROMPT = """You are a Product Manager creating business-value oriented release notes for Confluence.

Generate release notes in the following format:

# Release: {fix_version}

## TL;DR
- Key business outcomes.

## What's New
- Feature summaries by theme.

## Why It Matters
- Business/customer/regulatory impact.

## Links
- Jira Fix Version


If an EXAMPLE FORMAT is provided, match its structure and headings exactly; otherwise use the default template above."""


SLACK_ANNOUNCEMENT_PROMPT = """
You are a Product Manager announcing a new release to internal teams on Slack or Teams.

Write a concise announcement (under ~800 characters) focused on the **value and benefits** of this release — not a changelog.

Tone: confident, outcome-oriented, and relevant to users.

Format:
{fix_version} is live! 🚀
- 3 bullets summarising key benefits or improvements for users or stakeholders.
- Optional closing line or CTA (e.g. “Read the release notes for details” + link).

Avoid listing individual tickets or technical fixes. Highlight why this release matters.
Use emojis sparingly.
"""


def wrap_example_block(example: str) -> str:
    """Wrap example format in a delimited block."""
    return f"### EXAMPLE FORMAT START\n{example}\n### EXAMPLE FORMAT END"


def build_fix_version_prompt(
    tickets: list,
    project: str,
    fix_version: str,
    example_format: Optional[str] = None,
) -> list:
    """Build message array for Fix Version notes."""
    messages = [
        {
            "role": "system",
            "content": "You are a Release Manager creating Fix Version release notes for Jira.",
        },
        {
            "role": "user",
            "content": f"Project: {project}\nFix Version: {fix_version}\n\nTickets:\n{format_tickets_json(tickets)}",
        },
        {"role": "user", "content": JIRA_FIX_VERSION_PROMPT.format(project=project, fix_version=fix_version)},
    ]
    
    if example_format:
        messages.append({
            "role": "user",
            "content": wrap_example_block(example_format),
        })
    
    return messages


def build_confluence_prompt(
    tickets: list,
    project: str,
    fix_version: str,
    example_format: Optional[str] = None,
) -> list:
    """Build message array for Confluence notes."""
    messages = [
        {
            "role": "system",
            "content": "You are a Product Manager creating business-value oriented release notes for Confluence.",
        },
        {
            "role": "user",
            "content": f"Project: {project}\nFix Version: {fix_version}\n\nTickets:\n{format_tickets_json(tickets)}",
        },
        {"role": "user", "content": CONFLUENCE_PROMPT.format(project=project, fix_version=fix_version)},
    ]
    
    if example_format:
        messages.append({
            "role": "user",
            "content": wrap_example_block(example_format),
        })
    
    return messages


def build_slack_prompt(
    tickets: list,
    project: str,
    fix_version: str,
    example_format: Optional[str] = None,
) -> list:
    """Build message array for Slack announcement."""
    messages = [
        {
            "role": "system",
            "content": "You are a Communications Manager creating a brief announcement for Slack/Teams.",
        },
        {
            "role": "user",
            "content": f"Project: {project}\nFix Version: {fix_version}\n\nTickets:\n{format_tickets_json(tickets)}",
        },
        {"role": "user", "content": SLACK_ANNOUNCEMENT_PROMPT.format(project=project, fix_version=fix_version)},
    ]
    
    if example_format:
        messages.append({
            "role": "user",
            "content": wrap_example_block(example_format),
        })
    
    return messages


def format_tickets_json(tickets: list) -> str:
    """Format tickets as JSON-like string for the prompt."""
    import json
    return json.dumps(tickets, indent=2)

