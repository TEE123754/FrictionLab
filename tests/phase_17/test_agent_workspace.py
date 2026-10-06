"""Fixture agent admission, bounded dispatch and durable partial outcomes."""

from __future__ import annotations

import asyncio
import json
import os
import zipfile
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import httpx

from frictionlab import agent_workspace
from frictionlab.agent_workspace import AgentRequest, AgentWorkspace
from frictionlab.app import create_app
from frictionlab.planning.inference import InferenceSettings
from frictionlab.reporting import unexecuted_report, write_report


def test_real_fixture_agents_through_dashboard_api(tmp_path):
    from frictionlab.desktop_acceptance import agent_smoke

    root = Path(os.environ.get("FRICTIONLAB_PHASE17_EVIDENCE", tmp_path)) / "agent-workflow"
    assert agent_smoke(root) == 0
    receipt = json.loads((root / "acceptance.json").read_text(encoding="utf-8"))
    assert receipt["paid_requests"] == 0
    assert receipt["results"]["healthy"]["outcome"] == "completed"
    assert receipt["results"]["dead_button"]["outcome"] == "abandoned_patience"


def settings():
    return InferenceSettings(
        provider="morpheus",
        model="synthetic-test-model",
        allow_remote=True,
        share_sanitized_state=True,
        billing_acknowledged=True,
        max_requests=1,
    )


def test_missing_planner_blocks_with_report_without_browser_or_provider(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_workspace, "browser_path", lambda: None)
    monkeypatch.setattr(agent_workspace, "get_key", lambda provider: None)
    workspace = AgentWorkspace(tmp_path)
    id = workspace.submit(AgentRequest(persona="impatient_mobile", journey="checkout_review"))
    assert workspace.status(id)["status"] == "blocked"
    report = workspace.report(id)
    assert report["execution_status"] == "blocked"
    assert report["protection"]["target_requests"] == 0
    assert report["planner_decisions"] == []


def test_paid_provider_requires_per_run_acknowledgement(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_workspace, "browser_path", lambda: "synthetic-browser")
    monkeypatch.setattr(agent_workspace, "read_settings", lambda root: settings())
    monkeypatch.setattr(agent_workspace, "get_key", lambda provider: "synthetic-key")
    workspace = AgentWorkspace(tmp_path)
    id = workspace.submit(AgentRequest(persona="impatient_mobile", journey="checkout_review"))
    assert workspace.status(id)["status"] == "blocked"
    assert "Morpheus charges" in workspace.report(id)["terminal_reason"]
    assert workspace.tasks == {}


def test_fixture_job_passes_request_budget_and_preserves_report(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_workspace, "browser_path", lambda: "synthetic-browser")
    monkeypatch.setattr(agent_workspace, "read_settings", lambda root: settings())
    monkeypatch.setattr(agent_workspace, "get_key", lambda provider: "synthetic-key")
    observed = {}

    async def fake_run(resolved, **kwargs):
        observed.update(kwargs)
        report = unexecuted_report("Synthetic planner boundary", resolved).model_copy(
            update={"run_id": UUID(kwargs["session_id"])}
        )
        write_report(
            report,
            kwargs["artifact_root"],
            prepared_directory=True,
            output_directory=kwargs["artifact_root"] / kwargs["session_id"],
        )
        return SimpleNamespace(report=report)

    monkeypatch.setattr(agent_workspace, "run_persona", fake_run)

    async def run():
        workspace = AgentWorkspace(tmp_path)
        id = workspace.submit(
            AgentRequest(
                persona="enterprise_evaluator",
                journey="delivery_information",
                variant="dead_button",
                max_requests=3,
                max_runtime_seconds=60,
                account_usage_acknowledged=True,
            )
        )
        await workspace.tasks[id]
        assert workspace.report(id)["run_id"] == id
        assert workspace.status(id)["status"] == "blocked"
        assert (workspace.path(id) / "report.html").is_file()
        assert observed["inference"].max_requests == 3
        assert observed["inference"].max_runtime_seconds == 60
        assert observed["limits"].max_runtime_seconds == 60
        assert observed["limits"].max_steps == 3
        assert observed["limits"].max_tool_calls == 3
        assert observed["behavioral"] is True
        assert observed["variant"] == "dead_button"
        await workspace.close()

    asyncio.run(run())


def test_local_planner_requires_explicit_selection_without_starting_model(tmp_path, monkeypatch):
    monkeypatch.setattr(AgentWorkspace, "local_resources", lambda self: {
        "available": True, "model": "Qwen3-4B-Q4_K_M",
        "integrity_verified": False, "downloads_started": False,
    })
    monkeypatch.setattr(agent_workspace, "browser_path", lambda: "synthetic-browser")
    app = create_app(tmp_path, 8765, token="synthetic-token")

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8765",
            headers={"x-frictionlab-token": "synthetic-token"},
        ) as client:
            assert not (await client.get("/api/agents/readiness")).json()["ready_to_attempt"]
            assert (await client.post("/api/settings/local", json={})).status_code == 400
            response = await client.post("/api/settings/local", json={"resource_usage_acknowledged": True})
            assert response.status_code == 200
            assert response.json()["model_started"] is False
            ready = (await client.get("/api/agents/readiness")).json()
            assert ready["ready_to_attempt"] is True
            assert ready["capability_verified"] is False
            assert ready["local_resources"]["integrity_verified"] is False
            monkeypatch.setattr(AgentWorkspace, "local_resources", lambda self: {
                "available": False, "model": "Qwen3-4B-Q4_K_M",
            })
            assert not (await client.get("/api/agents/readiness")).json()["ready_to_attempt"]
            assert (await client.post("/api/settings/local", json={"resource_usage_acknowledged": True})).status_code == 400
        await app.state.agents.close()
        await app.state.assessments.close()
    asyncio.run(run())


def test_restart_updates_partial_report_and_exports(tmp_path):
    workspace = AgentWorkspace(tmp_path)
    id = str(__import__("uuid").uuid4())
    workspace.path(id).mkdir()
    workspace.blocked(id, "Synthetic report saved before restart")
    workspace.progress(id, "running", "Synthetic interrupted worker")
    recovered = AgentWorkspace(tmp_path)
    assert recovered.status(id)["status"] == "interrupted"
    assert recovered.report(id)["execution_status"] == "interrupted"
    assert recovered.report(id)["report_status"] == "partial"
    assert b"Saved report retained after restart" in (recovered.path(id) / "report.md").read_bytes()


def test_cancelled_job_retains_partial_report(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_workspace, "browser_path", lambda: "synthetic-browser")
    monkeypatch.setattr(agent_workspace, "read_settings", lambda root: settings())
    monkeypatch.setattr(agent_workspace, "get_key", lambda provider: "synthetic-key")
    started = asyncio.Event()

    async def slow_run(*args, **kwargs):
        started.set()
        await asyncio.sleep(999)

    monkeypatch.setattr(agent_workspace, "run_persona", slow_run)

    async def run():
        workspace = AgentWorkspace(tmp_path)
        id = workspace.submit(
            AgentRequest(
                persona="impatient_mobile",
                journey="checkout_review",
                account_usage_acknowledged=True,
            )
        )
        await started.wait()
        workspace.cancel(id)
        await workspace.tasks[id]
        assert workspace.status(id)["status"] == "cancelled"
        assert workspace.report(id)["execution_status"] == "cancelled"
        assert workspace.report(id)["protection"]["target_requests"] == 0
        await workspace.close()

    asyncio.run(run())


def test_dashboard_agent_api_blocks_without_key_and_exports_partial(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_workspace, "browser_path", lambda: None)
    monkeypatch.setattr(agent_workspace, "get_key", lambda provider: None)
    app = create_app(tmp_path, 8765, token="synthetic-token")

    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://127.0.0.1:8765",
            headers={"x-frictionlab-token": "synthetic-token"},
        ) as client:
            readiness = await client.get("/api/agents/readiness")
            assert readiness.status_code == 200
            assert readiness.json()["ready_to_attempt"] is False
            response = await client.post(
                "/api/agents",
                json={"persona": "impatient_mobile", "journey": "checkout_review"},
            )
            assert response.status_code == 202
            id = response.json()["id"]
            report = await client.get(f"/api/agents/{id}/report")
            assert report.json()["execution_status"] == "blocked"
            exported = await client.get(f"/api/agents/{id}/export/md")
            assert exported.status_code == 200
            assert b"No website was tested" in exported.content
            directory = app.state.agents.path(id)
            (directory / "evidence").mkdir()
            (directory / "evidence" / "shot.png").write_bytes(b"synthetic-png")
            payload = app.state.agents.report(id)
            payload["visual_evidence"] = [{"path": "evidence/shot.png"}]
            (directory / "report.json").write_text(json.dumps(payload), encoding="utf-8")
            image = await client.get(f"/api/agents/{id}/evidence/evidence/shot.png")
            assert image.content == b"synthetic-png"
            assert (await client.get(f"/api/agents/{id}/evidence/report.json")).status_code == 404
            archive = await client.get(f"/api/agents/{id}/export/zip")
            with zipfile.ZipFile(BytesIO(archive.content)) as bundle:
                assert "evidence/shot.png" in bundle.namelist()
                assert "report.json" in bundle.namelist()
            assert (await client.get("/api/agents")).json()[0]["status"] == "blocked"
            assert (await client.get("/api/agents/readiness", headers={"x-frictionlab-token": "bad"})).status_code == 403
        await app.state.agents.close()
        await app.state.assessments.close()

    asyncio.run(run())
