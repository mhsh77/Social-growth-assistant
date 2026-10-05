"""Thin wrapper around the Anthropic Messages API for JSON-shaped answers."""

from __future__ import annotations

import json
from typing import Any

import anthropic

# On a policy decline the API re-runs the request on a fallback model inside the same call.
_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMError(Exception):
    """The model call failed or returned something unusable; callers degrade gracefully."""


class Refused(LLMError):
    pass


def make_client() -> anthropic.Anthropic:
    # Reads ANTHROPIC_API_KEY from the environment (.env is loaded by the CLI).
    return anthropic.Anthropic()


def complete_json(
    client: Any,
    *,
    model: str,
    system: str,
    user: str,
    schema: dict,
    effort: str | None = None,
    max_tokens: int = 16000,
    refusal_fallback: bool = True,
) -> dict:
    """Ask for output matching `schema` (JSON Schema) and return the parsed object."""
    output_config: dict[str, Any] = {"format": {"type": "json_schema", "schema": schema}}
    if effort:
        output_config["effort"] = effort
    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "output_config": output_config,
    }
    if refusal_fallback:
        kwargs["betas"] = [_FALLBACK_BETA]
        kwargs["fallbacks"] = "default"

    try:
        response = client.beta.messages.create(**kwargs)
    except anthropic.AuthenticationError as err:
        raise LLMError("Anthropic API key missing or invalid (check .env).") from err
    except anthropic.BadRequestError as err:
        raise LLMError(f"Request rejected: {err.message}") from err
    except anthropic.RateLimitError as err:
        raise LLMError("Anthropic rate limit hit after retries; try again later.") from err
    except anthropic.APIStatusError as err:
        raise LLMError(f"Anthropic API error {err.status_code}.") from err
    except anthropic.APIConnectionError as err:
        raise LLMError("Can't reach the Anthropic API (network).") from err

    if response.stop_reason == "refusal":
        raise Refused("The model declined this request.")
    if response.stop_reason == "max_tokens":
        raise LLMError("Response was cut off (max_tokens).")
    text = next((b.text for b in response.content if b.type == "text"), None)
    if text is None:
        raise LLMError("Response had no text block.")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as err:
        raise LLMError("Response was not valid JSON.") from err
    if not isinstance(data, dict):
        raise LLMError("Response JSON was not an object.")
    return data
