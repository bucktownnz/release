"""Prompt templates for different release note formats."""

from typing import Optional


JIRA_FIX_VERSION_PROMPT = """You are a Release Manager creating Fix Version release notes for Jira.

Generate release notes in the following format:

# {project} – Fix Version {fix_version} – Release Notes

## Summary
1–2 sentences describing the overall change.

## Changes
- {{key}}: {{summary}}
  - (optional) User-facing sub-bullet if needed.

## Fix Version Description (Jira field)
3–5 sentences summarising the release.

If an EXAMPLE FORMAT is provided, match its structure and headings exactly; otherwise use the default template above."""


CONFLUENCE_PROMPT = """You are a Product Manager creating business-value oriented release notes for Confluence.

Generate release notes in the following format:

# {project} Release: {fix_version}

## TL;DR
- Key business outcomes.

## What's New
- Feature summaries by theme.

## Why It Matters
- Business/customer/regulatory impact.

## Rollout & Risk
- Deployment notes/placeholders.

## Links
- Jira Fix Version
- Dashboard
- Runbook

If an EXAMPLE FORMAT is provided, match its structure and headings exactly; otherwise use the default template above."""


SLACK_ANNOUNCEMENT_PROMPT = """You are a Communications Manager creating a brief announcement for Slack/Teams.

Generate a concise announcement (under ~800 characters) in the following format:

{project} Release {fix_version} is live! 🚀
- 3 bullets on user-facing improvements.
- Optional CTA or link.

Keep it brief, friendly, and actionable. Use emojis sparingly.

If an EXAMPLE FORMAT is provided, match its structure and headings exactly; otherwise use the default template above."""


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

