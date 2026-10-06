"""Offline smoke path used only to qualify the extracted Windows download."""

import json
import time
import zipfile
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import httpx

from frictionlab.launcher import LocalServer


def fixture_decision(request):
    """Scripted test double, never a real AI model or capability claim."""
    payload = json.loads(request.content)
    state = json.loads(next(m["content"] for m in payload["messages"] if m["role"] == "user"))
    fields = {"observation_id": state["observation_id"]}
    candidates = state["candidates"]
    textbox = next((c for c in candidates if c["role"] == "textbox"), None)
    button = next(
        (c for c in candidates if c["name"] in {"Continue to order review", "Start checkout"}),
        None,
    )
    if state["milestones"] and all(state["milestones"].values()):
        fields.update(kind="finish")
    elif textbox and not textbox.get("filled_text_reference"):
        fields.update(kind="type_text", candidate_id=textbox["id"], text_reference="synthetic_email")
    elif button:
        fields.update(kind="click", candidate_id=button["id"])
    else:
        fields.update(kind="scroll", direction="down", amount=400)
    return httpx.Response(
        200,
        json={
            "model": "scripted-fixture-test-double",
            "usage": {"total_tokens": 256},
            "choices": [{
                "finish_reason": "stop",
                "message": {"content": json.dumps({
                    "action": fields, "rationale": "Scripted acceptance action on observed fixture"
                })},
            }],
        },
    )


def agent_smoke(root=None):
    """Exercise dashboard → mocked provider → real fixture browser → export."""
    from frictionlab.assessment.service import save_settings
    from frictionlab.planning.cloud_transport import CloudModelRuntime
    from frictionlab.planning.inference import InferenceSettings

    root = Path(root) if root else Path.cwd() / "agent-smoke-workspace"
    save_settings(root, InferenceSettings(
        provider="groq", model="scripted-fixture-test-double", allow_remote=True,
        share_sanitized_state=True, free_tier_confirmed=True,
    ))
    server = LocalServer(root)
    results = {}

    def factory(settings):
        return CloudModelRuntime(settings, transport=httpx.MockTransport(fixture_decision))

    with (
        patch("frictionlab.agent_workspace.get_key", return_value="synthetic-fixture-key"),
        patch("frictionlab.planning.cloud_transport.provider_key", return_value="synthetic-fixture-key"),
        patch("frictionlab.planning.runner.CloudModelRuntime", side_effect=factory),
    ):
        server.start()
        try:
            for _ in range(200):
                if server.ready:
                    break
                time.sleep(0.05)
            assert server.ready
            with httpx.Client(base_url=server.url, trust_env=False, timeout=15) as client:
                headers = {"x-frictionlab-token": server.app.state.token}
                assert client.get("/api/agents/readiness", headers=headers).json()["ready_to_attempt"]
                for variant in ("healthy", "dead_button"):
                    response = client.post("/api/agents", headers=headers, json={
                        "persona": "impatient_mobile", "journey": "checkout_review",
                        "variant": variant, "max_requests": 12, "max_runtime_seconds": 120,
                        "account_usage_acknowledged": True,
                    })
                    assert response.status_code == 202
                    id = response.json()["id"]
                    deadline = time.monotonic() + 155
                    while time.monotonic() < deadline:
                        state = client.get(f"/api/agents/{id}", headers=headers).json()
                        if state["status"] not in {"queued", "running"}:
                            break
                        time.sleep(0.2)
                    else:
                        raise AssertionError("Fixture agent acceptance exceeded its deadline")
                    report = client.get(f"/api/agents/{id}/report", headers=headers).json()
                    protection = report["protection"]
                    assert report["execution_status"] == "completed", report["terminal_reason"]
                    assert protection["sentinel_requests"] == 0
                    assert protection["sentinel_data_unchanged"]
                    assert protection["network_boundary_validated"]
                    assert report["planner_decisions"] and report["trajectories"]
                    outcome = "completed" if variant == "healthy" else "abandoned_patience"
                    assert report["cohort_results"]["outcome_counts"] == {outcome: 1}
                    if variant != "healthy":
                        assert report["abandonment_diagnosis"] and report["friction_events"]
                    assert report["visual_evidence"]
                    for item in report["visual_evidence"][:1]:
                        image = client.get(f"/api/agents/{id}/evidence/{item['path']}", headers=headers)
                        assert image.status_code == 200 and image.content.startswith(b"\x89PNG")
                    export = client.get(f"/api/agents/{id}/export/zip", headers=headers)
                    assert export.status_code == 200 and export.content.startswith(b"PK")
                    with zipfile.ZipFile(BytesIO(export.content)) as bundle:
                        assert all(item["path"] in bundle.namelist() for item in report["visual_evidence"])
                        assert any(name.endswith(".dom.json") for name in bundle.namelist())
                    (root / f"{variant}-export.zip").write_bytes(export.content)
                    results[variant] = {"id": id, "outcome": outcome, "sentinel_requests": 0}
            # Review the actual shared UI, rather than only its report API.
            from playwright.sync_api import sync_playwright

            from frictionlab.assessment.render import browser_path

            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True, executable_path=browser_path())
                try:
                    page = browser.new_page(viewport={"width": 1280, "height": 900})
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.goto(server.url)
                    page.locator("#agent-history button").filter(
                        has_text=results["dead_button"]["id"][:8]
                    ).click()
                    page.locator("#agent-results h4").filter(
                        has_text="Findings and remediation"
                    ).wait_for()
                    timeline = page.locator("#agent-results details").filter(
                        has=page.locator("summary", has_text="Action timeline")
                    )
                    timeline.locator("summary").click()
                    first_action = report["trajectories"][0].get("action")
                    first_kind = first_action["kind"] if first_action else "unavailable"
                    assert f"Step 1: {first_kind}" in timeline.inner_text()
                    assert "undefined" not in page.locator("#agent-results").inner_text()
                    assert "Observed friction" in page.locator("#agent-results").inner_text()
                    page.screenshot(path=str(root / "agent-review.png"), full_page=True)
                    assert not errors, errors
                finally:
                    browser.close()
            (root / "acceptance.json").write_text(json.dumps({
                "provider": "scripted test double; no real inference",
                "paid_requests": 0, "results": results, "dashboard_review": "passed",
            }, indent=2), encoding="utf-8")
            return 0
        finally:
            server.stop()
            server.thread.join(60)


def smoke():
    server = LocalServer(Path.cwd() / "smoke-workspace")
    server.start()
    try:
        for _ in range(200):
            if server.ready:
                break
            time.sleep(0.05)
        assert server.ready
        with httpx.Client(base_url=server.url, trust_env=False) as client:
            assert "New assessment" in client.get("/").text
            headers = {"x-frictionlab-token": server.app.state.token}
            response = client.post(
                "/api/assessments",
                headers=headers,
                json={
                    "url": "https://example.com",
                    "mode": "snapshot",
                    "html": '<html lang="en"><title>Desktop test</title><h1>Desktop</h1></html>',
                },
            )
            assert response.status_code == 202
            id = response.json()["id"]
            for _ in range(400):
                state = client.get(f"/api/assessments/{id}", headers=headers).json()
                if state["status"] not in {"queued", "running"}:
                    break
                time.sleep(0.1)
            report = client.get(f"/api/assessments/{id}/report", headers=headers).json()
            assert report["execution_status"] == "completed"
            assert report["acquisition"]["target_requests"] == 0
            assert len(report["evidence_files"]) == 3
            assert not any(c["id"].endswith(".renderer") for c in report["checks"])
        return 0
    finally:
        server.stop()
        server.thread.join(60)
