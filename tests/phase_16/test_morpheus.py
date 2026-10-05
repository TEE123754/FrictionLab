"""Morpheus stays bounded and credentials remain outside reports and settings."""

import asyncio
import json
import time

import httpx
import pytest

from frictionlab import configuration
from frictionlab.app import Connection, connect
from frictionlab.assessment.service import read_settings
from frictionlab.credentials import get_key
from frictionlab.planning.cloud_transport import CloudModelRuntime
from frictionlab.planning.contracts import PlannerStopped
from frictionlab.planning.inference import InferenceSettings, safe_text


def settings(**updates):
    values = {
        "provider": "morpheus",
        "model": "fixture-model",
        "allow_remote": True,
        "share_sanitized_state": True,
        "billing_acknowledged": True,
        "max_requests": 1,
        "max_tokens": 4096,
        "max_retries": 0,
    }
    return InferenceSettings(**(values | updates))


def test_billing_acknowledgement_is_required():
    with pytest.raises(ValueError):
        settings(billing_acknowledged=False)


def test_ignored_env_key_connects_without_being_saved_or_returned(tmp_path, monkeypatch):
    secret = "synthetic-morpheus-key-for-test"
    (tmp_path / ".env").write_text(
        "MORPHEUS_API_KEY=" + secret + "\nMORPHEUS_BASE_URL=https://api.mor.org/api/v1\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(configuration, "ROOT", tmp_path)
    monkeypatch.delenv("MORPHEUS_API_KEY", raising=False)
    connect(
        tmp_path,
        Connection(
            provider="morpheus",
            model="fixture-model",
            use_local_env=True,
            share_findings=True,
            billing_acknowledged=True,
        ),
    )
    saved = (tmp_path / "app-settings.json").read_text(encoding="utf-8")
    assert secret not in saved
    assert read_settings(tmp_path).provider == "morpheus"
    assert get_key("morpheus") == secret
    assert secret not in safe_text("provider said " + secret)
    assert "[redacted credential]" in safe_text("provider said " + secret)


def test_one_mocked_request_uses_fixed_endpoint_and_stops_at_budget(monkeypatch):
    monkeypatch.setenv("MORPHEUS_API_KEY", "synthetic-morpheus-key-for-test")
    monkeypatch.setenv("MORPHEUS_BASE_URL", "https://api.mor.org/api/v1")
    seen = []

    def respond(request):
        seen.append((str(request.url), request.headers.get("Authorization")))
        return httpx.Response(
            200,
            json={
                "model": "fixture-model",
                "usage": {"total_tokens": 25},
                "choices": [
                    {"finish_reason": "stop", "message": {"content": '{"ok":true}'}}
                ],
            },
        )

    async def run():
        runtime = CloudModelRuntime(settings(), transport=httpx.MockTransport(respond))
        await runtime.__aenter__()
        try:
            body = runtime.complete(
                [{"role": "user", "content": "synthetic"}], 32, time.monotonic() + 5
            )
            assert json.loads(body["choices"][0]["message"]["content"]) == {"ok": True}
            assert seen[0][0] == "https://api.mor.org/api/v1/chat/completions"
            assert seen[0][1] == "Bearer synthetic-morpheus-key-for-test"
            with pytest.raises(PlannerStopped) as exc:
                runtime.complete([{"role": "user", "content": "again"}], 32, time.monotonic() + 5)
            assert exc.value.category == "cloud_budget_paused"
            assert len(seen) == 1
        finally:
            await runtime.close()

    asyncio.run(run())


def test_custom_host_is_rejected_before_dispatch(monkeypatch):
    from frictionlab.credentials import morpheus_base_url

    monkeypatch.setenv("MORPHEUS_BASE_URL", "https://untrusted.example/v1")
    with pytest.raises(ValueError):
        morpheus_base_url()
