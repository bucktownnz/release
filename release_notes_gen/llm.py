"""OpenAI API integration with retry logic."""

import os
from typing import List, Dict, Optional

import httpx
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


def _parse_version(version: str) -> tuple[int, ...]:
    parts = []
    for piece in version.split("."):
        digits = ""
        for ch in piece:
            if ch.isdigit():
                digits += ch
            else:
                break
        if digits:
            parts.append(int(digits))
    return tuple(parts)


def _build_httpx_client() -> httpx.Client:
    """Construct an httpx.Client compatible with the installed version."""
    httpx_version = _parse_version(httpx.__version__)
    proxy_url = (
        os.getenv("HTTPS_PROXY")
        or os.getenv("https_proxy")
        or os.getenv("HTTP_PROXY")
        or os.getenv("http_proxy")
    )

    client_kwargs = {}
    if proxy_url:
        if httpx_version >= (0, 28):
            client_kwargs["proxy"] = proxy_url
        else:
            client_kwargs["proxies"] = proxy_url

    return httpx.Client(**client_kwargs)


def get_openai_client() -> OpenAI:
    """Get OpenAI client with API key from environment."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY environment variable not set. "
            "Set it or create a .env file with OPENAI_API_KEY=sk-..."
        )
    http_client = _build_httpx_client()
    return OpenAI(api_key=api_key, http_client=http_client)


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


def chat_completion(
    messages: List[Dict[str, str]],
    model: str = "gpt-4o-mini",
    max_tokens: int = 2000,
    temperature: float = 0.2,
) -> str:
    """
    Perform a chat completion request using the shared retry-aware client.

    Args:
        messages: Message list for the chat completion.
        model: OpenAI model name.
        max_tokens: Response token limit.
        temperature: Sampling temperature.

    Returns:
        Response content as a string (stripped).
    """
    return _call_openai(messages, model, max_tokens, temperature)


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

