"""Approval cards carry plain-language context (tools/approval_card.py).

Kind (emoji title), reversibility, an opening sentence and an explanation, written by the auxiliary
``approval`` model from the real action and the asking chat — only when a human is about to be asked.
"""

import json
from types import SimpleNamespace

import pytest

import tools.approval_card as ac


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
    monkeypatch.setattr(aux, "get_text_auxiliary_client", lambda task="", **kw: (object(), "m"))


@pytest.fixture(autouse=True)
def _spanish_no_chat(monkeypatch):
    monkeypatch.setattr(ac, "_lang", lambda: "es")
    monkeypatch.setattr(ac, "chat_excerpt", lambda sk: ("Auditoría", "USER: arreglá el guardián"))
    monkeypatch.setattr(ac, "_cfg", lambda: {})


MODEL_JSON = json.dumps({"kind": "internal", "reversible": "yes",
                         "opening": "El chat «Auditoría» pide permiso para corregir una falsa alarma.",
                         "explanation": "El guardián es un programa...\n\nSi rechazás no pasa nada."})


def test_card_has_emoji_title_reversibility_and_text(monkeypatch):
    seen = []
    _fake_llm(monkeypatch, text="Here you go:\n" + MODEL_JSON, seen=seen)
    card = ac.build_card({"command": "python registro.py actualizar X", "description": "script via -c"}, "a:b:local-1")
    assert card["title"] == "🔧 Ajuste interno de Hermes"
    assert card["reversible_label"] == "se puede deshacer"
    assert card["opening"].startswith("El chat «Auditoría»")
    assert card["explain_label"] == "Explicación" and card["command_label"] == "Ver comando técnico"
    # untrusted framing, chat title and thinking off
    msgs = seen[0]["messages"]
    assert "UNTRUSTED" in msgs[0]["content"] and "Spanish" in msgs[0]["content"]
    assert "<chat_title>Auditoría</chat_title>" in msgs[1]["content"] and "<action>" in msgs[1]["content"]
    assert seen[0]["reasoning_config"] == {"enabled": False}


def test_unknown_kind_falls_back_to_pattern(monkeypatch):
    _fake_llm(monkeypatch, text=json.dumps({"kind": "weird", "opening": "x"}))
    card = ac.build_card({"command": "reg add HKCU\\X", "description": "registry write"}, "s")
    assert card["title"] == "🪟 Tu Windows"


def test_model_failure_uses_deterministic_kind_or_nothing(monkeypatch):
    _fake_llm(monkeypatch, exc=RuntimeError("down"))
    card = ac.build_card({"command": "<write to SOUL.md>", "pattern_key": "protected_instruction_file"}, "s")
    assert card["title"] == "🧠 Instrucciones de los agentes" and card["opening"] == ""
    assert ac.build_card({"command": "ls", "description": "something"}, "s") is None


def test_disabled_and_attach_strips_preview(monkeypatch):
    _fake_llm(monkeypatch, text=MODEL_JSON)
    data = ac.attach_card({"command": "c", "change_preview": "-a\n+b"}, "s")
    assert "change_preview" not in data and data["card"]["change_stats"].startswith("-1 / +1")
    monkeypatch.setattr(ac, "_cfg", lambda: {"context_card": False})
    data = ac.attach_card({"command": "c", "change_preview": "-a"}, "s")
    assert "card" not in data and "change_preview" not in data


def test_gateway_wait_attaches_card_before_notifying(monkeypatch):
    from tools import approval_gateway_wait as gw
    _fake_llm(monkeypatch, text=MODEL_JSON)
    sent = []

    def notify(data):
        sent.append(data)
        raise RuntimeError("stop here")  # notify failure ends the wait at once

    res = gw._await_gateway_decision("agent:main:local:dm:local-x", notify,
                                     {"command": "python -c 1", "pattern_key": "k", "pattern_keys": ["k"],
                                      "description": "d", "change_preview": "-x"})
    assert res.get("notify_failed")
    assert sent and sent[0]["card"]["opening"].startswith("El chat")
    assert "change_preview" not in sent[0]


def test_protected_write_gateway_passes_diff_not_summary(tmp_path, monkeypatch):
    import tools.approval as approval
    import tools.approval_gateway_wait as gw
    import tools.file_tools_write_guards as guards
    from tools.file_tools import write_file_tool

    monkeypatch.setattr(guards, "_protected_instruction_config", lambda: (True, []))
    monkeypatch.setattr(approval, "_gateway_notify_cb", lambda sk: (lambda d: None))
    captured = {}

    def fake_wait(session_key, notify_cb, approval_data, surface="gateway", identity=None):
        captured.update(approval_data)
        return {"resolved": True, "choice": "deny"}

    monkeypatch.setattr(gw, "_await_gateway_decision", fake_wait)
    target = tmp_path / "SOUL.md"
    target.write_text("## A\nold rule\n", encoding="utf-8")
    res = json.loads(write_file_tool(str(target), "## A\nnew rule\n"))
    assert "denied" in res["error"]
    assert "-old rule" in captured["change_preview"] and "+new rule" in captured["change_preview"]
    assert captured["command"] == "<write to SOUL.md>"
