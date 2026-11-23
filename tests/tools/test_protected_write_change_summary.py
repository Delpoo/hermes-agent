"""The protected-instruction approval card describes the change, not only the file name.

Before: the card read ``<write to SOUL.md>``, so the approver could not tell an added line from a
deleted rule set. Now the description carries a summary of the real diff (auxiliary ``approval``
model) plus deterministic line/heading counts, and the label switches to the synthetic
``<...> (`` form that surfaces render as "details".
"""

import json
from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def _interactive_cli(monkeypatch):
    import tools.file_tools_write_guards as guards
    from tools import approval_context
    from tools.terminal_tool import set_approval_callback
    monkeypatch.setattr(guards, "_protected_instruction_config", lambda: (True, []))
    for name in ("HERMES_SINGLE_QUERY_SESSION", "HERMES_CRON_SESSION", "HERMES_SESSION_PLATFORM"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(approval_context, "_no_user_can_answer", lambda: False)
    yield
    set_approval_callback(None)


def _fake_llm(monkeypatch, text=None, exc=None, seen=None):
    import agent.auxiliary_client as aux

    def call_llm(**kwargs):
        if seen is not None:
            seen.append(kwargs)
        if exc:
            raise exc
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])

    monkeypatch.setattr(aux, "call_llm", call_llm)
    monkeypatch.setattr(aux, "_get_task_timeout", lambda task: 5)


def _ask(monkeypatch, answer):
    from tools.terminal_tool import set_approval_callback
    asked = []
    set_approval_callback(lambda command, description, **kw: asked.append((command, description)) or answer)
    return asked


OLD = "# Rules\n\n## Blockers\nAlways list five facts.\nInclude them in agent reports.\n\n## Style\nBe brief.\n"


def test_write_file_card_carries_summary_and_counts(tmp_path, monkeypatch):
    from tools.file_tools import write_file_tool
    seen = []
    _fake_llm(monkeypatch, text="Replaces the Blockers section; removes the five-facts rule.", seen=seen)
    asked = _ask(monkeypatch, "deny")
    target = tmp_path / "SOUL.md"
    target.write_text(OLD, encoding="utf-8")

    res = json.loads(write_file_tool(str(target), "# Rules\n\n## Style\nBe brief.\n"))

    assert "denied" in res["error"]
    assert target.read_text(encoding="utf-8") == OLD
    command, description = asked[0]
    assert command.startswith("<write to SOUL.md> (")
    assert "removes the five-facts rule" in description
    assert "-4 / +0" in description
    assert "− Blockers" in description
    # the real diff, not the agent's words, reaches the summarizer — wrapped as untrusted data
    user_msg = seen[0]["messages"][1]["content"]
    assert "<change>" in user_msg and "-Always list five facts." in user_msg
    assert "UNTRUSTED" in seen[0]["messages"][0]["content"]


def test_patch_replace_preview_is_the_replaced_region(tmp_path, monkeypatch):
    from tools.file_tools import patch_tool
    seen = []
    _fake_llm(monkeypatch, text="Adds one line.", seen=seen)
    asked = _ask(monkeypatch, "once")
    target = tmp_path / "AGENTS.md"
    target.write_text(OLD, encoding="utf-8")

    res = json.loads(patch_tool(mode="replace", path=str(target), old_string="Be brief.",
                                new_string="Be brief.\nCite sources."))

    assert not res.get("error")
    assert "Cite sources." in target.read_text(encoding="utf-8")
    assert "+Cite sources." in seen[0]["messages"][1]["content"]
    assert "Adds one line." in asked[0][1]


def test_v4a_multi_file_patch_is_one_prompt_with_one_summary(tmp_path, monkeypatch):
    from tools.file_tools import patch_tool
    seen = []
    _fake_llm(monkeypatch, text="Adds a rule to both profiles.", seen=seen)
    asked = _ask(monkeypatch, "deny")
    a, b = tmp_path / "p1" / "SOUL.md", tmp_path / "p2" / "SOUL.md"
    for f in (a, b):
        f.parent.mkdir()
        f.write_text("## Style\nBe brief.\n", encoding="utf-8")
    patch = (f"*** Begin Patch\n*** Update File: {a}\n@@\n ## Style\n Be brief.\n+New rule.\n"
             f"*** Update File: {b}\n@@\n ## Style\n Be brief.\n+New rule.\n*** End Patch")

    res = json.loads(patch_tool(mode="patch", patch=patch))

    assert "denied" in res["error"]
    assert len(asked) == 1 and len(seen) == 1
    assert "Adds a rule to both profiles." in asked[0][1]
    assert "-0 / +2" in asked[0][1]


def test_summarizer_failure_falls_back_to_counts(tmp_path, monkeypatch):
    from tools.file_tools import write_file_tool
    _fake_llm(monkeypatch, exc=RuntimeError("provider down"))
    asked = _ask(monkeypatch, "deny")
    target = tmp_path / "SOUL.md"
    target.write_text(OLD, encoding="utf-8")

    write_file_tool(str(target), OLD + "Extra.\n")

    command, description = asked[0]
    assert command.startswith("<write to SOUL.md> (")
    assert "-0 / +1" in description


def test_disabled_keeps_the_old_card(tmp_path, monkeypatch):
    from tools import approval_context
    from tools.file_tools import write_file_tool
    seen = []
    _fake_llm(monkeypatch, text="x", seen=seen)
    monkeypatch.setattr(approval_context, "_get_approval_config", lambda: {"protected_write_summary": False})
    asked = _ask(monkeypatch, "deny")
    target = tmp_path / "SOUL.md"
    target.write_text(OLD, encoding="utf-8")

    write_file_tool(str(target), "new")

    assert seen == []
    assert asked[0][0] == "<write to SOUL.md>"


def test_non_protected_write_never_builds_a_preview(tmp_path, monkeypatch):
    from tools.file_tools import write_file_tool
    seen = []
    _fake_llm(monkeypatch, text="x", seen=seen)
    target = tmp_path / "notes.md"

    res = json.loads(write_file_tool(str(target), "hello"))

    assert not res.get("error") and seen == []
