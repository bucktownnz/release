"""OpenAI API integration with retry logic."""

import os
from typing import List, Dict, Optional
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
from openai import OpenAI
from openai import RateLimitError, APIError

from .prompts import (
    build_fix_version_prompt,
    build_confluence_prompt,
    build_slack_prompt,
)


def get_openai_client() -> OpenAI:
    """Get OpenAI client with API key from environment."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY environment variable not set. "
            "Set it or create a .env file with OPENAI_API_KEY=sk-..."
        )
    return OpenAI(api_key=api_key)


@retry(
    retry=retry_if_exception_type((RateLimitError, APIError)),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    reraise=True,
)
def _call_openai(
    messages: List[Dict[str, str]],
    model: str = "gpt-4o-mini",
    max_tokens: int = 2000,
    temperature: float = 0.2,
) -> str:
    """Make OpenAI API call with retry logic."""
    client = get_openai_client()
    
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    
    return response.choices[0].message.content.strip()


def generate_fix_version_notes(
    tickets: List[Dict[str, Optional[str]]],
    project: str,
    fix_version: str,
    model: str = "gpt-4o-mini",
    max_tokens: int = 2000,
    temperature: float = 0.2,
    example_format: Optional[str] = None,
) -> str:
    """Generate Jira Fix Version release notes."""
    messages = build_fix_version_prompt(tickets, project, fix_version, example_format)
    return _call_openai(messages, model, max_tokens, temperature)


def generate_confluence_notes(
    tickets: List[Dict[str, Optional[str]]],
    project: str,
    fix_version: str,
    model: str = "gpt-4o-mini",
    max_tokens: int = 2000,
    temperature: float = 0.2,
    example_format: Optional[str] = None,
) -> str:
    """Generate Confluence release notes."""
    messages = build_confluence_prompt(tickets, project, fix_version, example_format)
    return _call_openai(messages, model, max_tokens, temperature)


def generate_slack_announcement(
    tickets: List[Dict[str, Optional[str]]],
    project: str,
    fix_version: str,
    model: str = "gpt-4o-mini",
    max_tokens: int = 2000,
    temperature: float = 0.2,
    example_format: Optional[str] = None,
) -> str:
    """Generate Slack/Teams announcement."""
    messages = build_slack_prompt(tickets, project, fix_version, example_format)
    return _call_openai(messages, model, max_tokens, temperature)

