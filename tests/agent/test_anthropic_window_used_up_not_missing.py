"""A used-up Claude window (per-model 429 benches on a sole OAuth seat) is a cooldown, not a
missing or rejected credential.

Before the fix the model-less pool probe treated ANY active model cooldown as "no credential":
haiku could not resolve while only opus was benched, ``_anthropic_token_or_raise`` raised the
generic "No Anthropic credentials found", and the gateway stamped it ``auth_permanent`` so the
desktop said "rejected your API key".
"""
import json
import time

import pytest

TOKEN = "sk-ant-oat01-" + "x" * 40
MODEL_A = "claude-opus-4-5"
MODEL_B = "claude-haiku-4-5"


@pytest.fixture
def pool(tmp_path, monkeypatch):
    root = tmp_path / "hermes-root"
    root.mkdir()
    (tmp_path / "fakehome").mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "fakehome"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "fakehome"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "fakehome"))
    for var in ("ANTHROPIC_TOKEN", "ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HERMES_HOME", str(root))
    import hermes_constants
    hermes_constants._default_hermes_root_memo = None  # type: ignore[attr-defined]
    (root / "auth.json").write_text(json.dumps({"credential_pool": {"anthropic": [{
        "id": "seat", "label": "anthropic-oauth-1", "auth_type": "oauth", "priority": 0,
        "source": "manual:hermes_pkce", "base_url": "https://api.anthropic.com", "access_token": TOKEN, "refresh_token": "r" * 20,
        "expires_at_ms": int((time.time() + 3600) * 1000),
    }]}}))
    from agent.credential_pool import load_pool
    p = load_pool("anthropic")
    ctx = {"message": "This request would exceed your account's rate limit. Please try again later."}
    p.mark_exhausted_and_rotate(status_code=429, error_context=ctx, api_key_hint=TOKEN,
                                failure_reason="rate_limit", model=MODEL_A)
    return p


def test_unbenched_model_still_resolves(pool):
    from agent.anthropic_credentials import resolve_anthropic_token
    assert resolve_anthropic_token(model=MODEL_A) is None
    assert resolve_anthropic_token(model=MODEL_B) == TOKEN


def test_benched_model_raises_retryable_rate_limit_not_missing_credential(pool):
    from hermes_cli.auth_constants import AuthError
    from hermes_cli.runtime_provider import _anthropic_token_or_raise
    with pytest.raises(AuthError) as info:
        _anthropic_token_or_raise(model=MODEL_A)
    assert info.value.code == "model_rate_limited"
    assert info.value.retryable is True
    assert info.value.retry_after and info.value.retry_after > 0


def test_gateway_maps_benched_model_to_rate_limit(pool):
    from agent.error_classifier import FailoverReason
    from gateway.config import Platform
    from gateway.run_turn_runner import _resolution_failure_reply
    from hermes_cli.auth_constants import AuthError
    exc = AuthError("rate-limited", provider="anthropic", code="model_rate_limited", retry_after=60.0, retryable=True)
    _text, reason, retryable = _resolution_failure_reply(exc, Platform.LOCAL)
    assert reason == FailoverReason.rate_limit.value
    assert retryable is True


def test_truly_missing_credential_is_still_permanent(tmp_path, monkeypatch):
    root = tmp_path / "empty-root"
    root.mkdir()
    (tmp_path / "fakehome2").mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "fakehome2"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "fakehome2"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "fakehome2"))
    for var in ("ANTHROPIC_TOKEN", "ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HERMES_HOME", str(root))
    import hermes_constants
    hermes_constants._default_hermes_root_memo = None  # type: ignore[attr-defined]
    from hermes_cli.auth_constants import AuthError
    from hermes_cli.runtime_provider import _anthropic_token_or_raise
    with pytest.raises(AuthError) as info:
        _anthropic_token_or_raise(model=MODEL_A)
    assert info.value.code != "model_rate_limited"
