"""One real local-model journey through the shared dashboard API, on disposable CI."""

import json
import time
from pathlib import Path

import httpx

from frictionlab.launcher import LocalServer


def main():
    root = Path("artifacts/phase17/local-planner")
    server = LocalServer(root)
    server.start()
    try:
        deadline = time.monotonic() + 30
        while not server.ready and time.monotonic() < deadline:
            time.sleep(0.1)
        assert server.ready
        with httpx.Client(base_url=server.url, trust_env=False, timeout=15) as client:
            headers = {"x-frictionlab-token": server.app.state.token}
            response = client.post("/api/settings/local", headers=headers, json={
                "resource_usage_acknowledged": True,
            })
            assert response.status_code == 200, response.text
            assert response.json()["model_started"] is False
            ready = client.get("/api/agents/readiness", headers=headers).json()
            assert ready["ready_to_attempt"] and not ready["capability_verified"]
            started = client.post("/api/agents", headers=headers, json={
                "persona": "impatient_mobile", "journey": "checkout_review",
                "variant": "healthy", "max_requests": 12, "max_runtime_seconds": 240,
                "account_usage_acknowledged": True,
            })
            assert started.status_code == 202
            id = started.json()["id"]
            deadline = time.monotonic() + 330
            while time.monotonic() < deadline:
                state = client.get(f"/api/agents/{id}", headers=headers).json()
                if state["status"] not in {"queued", "running"}:
                    break
                time.sleep(0.5)
            else:
                raise AssertionError("Local model acceptance exceeded the bounded deadline")
            report = client.get(f"/api/agents/{id}/report", headers=headers).json()
            (root / "observed.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            assert report["execution_status"] == "completed", report["terminal_reason"]
            assert report["cohort_results"]["outcome_counts"] == {"completed": 1}
            assert report["planner_decisions"] and report["trajectories"]
            assert report["protection"]["sentinel_requests"] == 0
            assert report["protection"]["sentinel_data_unchanged"]
            assert report["protection"]["network_boundary_validated"]
            exported = client.get(f"/api/agents/{id}/export/zip", headers=headers)
            assert exported.status_code == 200
            (root / "report-export.zip").write_bytes(exported.content)
            (root / "acceptance.json").write_text(json.dumps({
                "run_id": id, "model": "pinned local Qwen3-4B-Q4_K_M",
                "real_local_inference": True, "paid_requests": 0,
                "outcome": "completed", "sentinel_requests": 0,
                "scope": "shared dashboard API, Linux source; frozen local-model path unqualified",
            }, indent=2), encoding="utf-8")
    finally:
        server.stop()
        server.thread.join(60)


if __name__ == "__main__":
    main()
