"""JSON-shaped model calls through either the Claude Code CLI or the Anthropic API.

The default backend runs `claude -p` (Claude Code's non-interactive mode), so calls use
the subscription you're logged in with and no API key is needed. The `api` backend uses
the Anthropic SDK and ANTHROPIC_API_KEY.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import anthropic

if TYPE_CHECKING:
    from .config import LLM

# On a policy decline the API re-runs the request on a fallback model inside the same call.
_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMError(Exception):
    """The model call failed or returned something unusable; callers degrade gracefully."""


class Refused(LLMError):
    pass


class ClaudeCli:
    """Backend that shells out to the `claude` CLI with tools disabled and a JSON schema."""

    def __init__(
        self,
        executable: str = "claude",
        timeout: float = 300,
        runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    ):
        self.executable = executable
        self.timeout = timeout
        self.runner = runner

    def command(self, model: str, system: str, schema: dict, effort: str | None) -> list[str]:
        cmd = [
            self.executable,
            "-p",
            "--output-format", "json",
            "--json-schema", json.dumps(schema),
            "--system-prompt", system,
            "--model", model,
            "--tools", "",  # a pure text task: no file, shell or web access
            "--strict-mcp-config",  # and no MCP servers from your settings
            "--no-session-persistence",
        ]  # fmt: skip
        if effort:
            cmd += ["--effort", effort]
        return cmd

    def complete_json(
        self, *, model: str, system: str, user: str, schema: dict, effort: str | None = None
    ) -> dict:
        env = dict(os.environ)
        # If an API key is set the CLI bills it instead of your logged-in subscription.
        env.pop("ANTHROPIC_API_KEY", None)
        try:
            proc = self.runner(
                self.command(model, system, schema, effort),
                input=user,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env=env,
                cwd=tempfile.gettempdir(),  # keep project CLAUDE.md files out of the prompt
            )
        except FileNotFoundError as err:
            raise LLMError(
                f"`{self.executable}` not found. Install Claude Code, then run `claude` "
                "once to log in."
            ) from err
        except subprocess.TimeoutExpired as err:
            raise LLMError(f"claude CLI timed out after {self.timeout:.0f}s.") from err

        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError as err:
            detail = (proc.stderr or proc.stdout or "").strip()[:300]
            raise LLMError(
                f"claude CLI failed: {detail or f'exit code {proc.returncode}'}"
            ) from err
        if not isinstance(data, dict):
            raise LLMError("claude CLI returned unexpected output.")
        if data.get("stop_reason") == "refusal":
            raise Refused("The model declined this request.")
        if data.get("is_error"):
            detail = str(data.get("result") or data.get("subtype") or "unknown error")[:300]
            raise LLMError(f"claude CLI error: {detail}")
        result = data.get("structured_output")
        if not isinstance(result, dict):
            try:
                result = json.loads(data.get("result") or "")
            except (TypeError, json.JSONDecodeError) as err:
                raise LLMError("claude CLI response was not valid JSON.") from err
        if not isinstance(result, dict):
            raise LLMError("Response JSON was not an object.")
        return result


def make_client(settings: LLM) -> Any:
    if settings.backend == "api":
        # Reads ANTHROPIC_API_KEY from the environment (.env is loaded by the CLI).
        return anthropic.Anthropic()
    return ClaudeCli(settings.claude_path, settings.timeout_seconds)


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
    if isinstance(client, ClaudeCli):
        return client.complete_json(
            model=model, system=system, user=user, schema=schema, effort=effort
        )
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
