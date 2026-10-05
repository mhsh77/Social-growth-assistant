import json
import subprocess

import pytest

from sga.config import LLM
from sga.llm import ClaudeCli, LLMError, Refused, complete_json, make_client

SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}}


def fake_runner(stdout="", stderr="", returncode=0, raises=None, seen=None):
    def run(cmd, **kwargs):
        if seen is not None:
            seen.update(cmd=cmd, **kwargs)
        if raises:
            raise raises
        return subprocess.CompletedProcess(cmd, returncode, stdout, stderr)

    return run


def call(runner):
    cli = ClaudeCli(runner=runner)
    return complete_json(
        cli, model="claude-opus-5-5", system="sys", user="msg", schema=SCHEMA, effort="low"
    )


def test_builds_a_tool_free_structured_call_and_sends_prompt_on_stdin(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-leak")
    seen = {}
    out = json.dumps({"is_error": False, "structured_output": {"ok": True}})
    assert call(fake_runner(out, seen=seen)) == {"ok": True}
    cmd = seen["cmd"]
    assert cmd[:2] == ["claude", "-p"]
    assert cmd[cmd.index("--tools") + 1] == ""
    assert json.loads(cmd[cmd.index("--json-schema") + 1]) == SCHEMA
    assert cmd[cmd.index("--model") + 1] == "claude-opus-5-5"
    assert cmd[cmd.index("--effort") + 1] == "low"
    assert seen["input"] == "msg"
    assert "ANTHROPIC_API_KEY" not in seen["env"]  # subscription login, not the API key


def test_falls_back_to_result_text_when_no_structured_output():
    out = json.dumps({"is_error": False, "result": '{"ok": false}'})
    assert call(fake_runner(out)) == {"ok": False}


@pytest.mark.parametrize(
    "runner, message",
    [
        (fake_runner(raises=FileNotFoundError()), "not found"),
        (fake_runner(raises=subprocess.TimeoutExpired("claude", 1)), "timed out"),
        (fake_runner("", "Please run /login", 1), "Please run /login"),
        (
            fake_runner(json.dumps({"is_error": True, "result": "Usage limit reached"})),
            "Usage limit reached",
        ),
        (fake_runner(json.dumps({"is_error": False, "result": "plain words"})), "not valid JSON"),
    ],
)
def test_failures_become_llm_errors(runner, message):
    with pytest.raises(LLMError, match=message):
        call(runner)


def test_refusal():
    with pytest.raises(Refused):
        call(fake_runner(json.dumps({"stop_reason": "refusal", "is_error": False})))


def test_make_client_picks_backend():
    assert isinstance(make_client(LLM()), ClaudeCli)
    cli = make_client(LLM(claude_path="/opt/claude", timeout_seconds=12))
    assert (cli.executable, cli.timeout) == ("/opt/claude", 12)
