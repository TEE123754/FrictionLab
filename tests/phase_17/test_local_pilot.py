"""One local-only pilot over three owned offline SPA page states."""

from __future__ import annotations

import asyncio
import json
import os
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path

from frictionlab.assessment.models import CATEGORIES, AssessmentRequest
from frictionlab.assessment.report import export_zip
from frictionlab.assessment.service import Assessments
from frictionlab.product import doctor

PAGES = Path(__file__).resolve().parents[2] / "examples" / "phase17-pilots"


def test_first_run_assessment_diagnostics_require_no_model_or_key():
    result = doctor()
    assert result["ready_for_assessment"] is True
    assert result["network_requests"] == 0
    assert result["downloads"] is False
    assert result["models_started"] is False


def test_three_offline_pilots_report_evidence_and_zero_contact(tmp_path):
    contacts = []

    class Sentinel(BaseHTTPRequestHandler):
        def do_GET(self):
            contacts.append(self.path)
            self.send_response(200)
            self.end_headers()

        do_POST = do_GET

        def log_message(self, *args):
            pass

    sentinel = ThreadingHTTPServer(("127.0.0.1", 0), Sentinel)
    thread = threading.Thread(target=sentinel.serve_forever, daemon=True)
    thread.start()
    evidence_root = Path(os.environ.get("FRICTIONLAB_PHASE17_EVIDENCE", tmp_path)).resolve()
    evidence_root.mkdir(parents=True, exist_ok=True)

    async def run():
        service = Assessments(evidence_root)
        reports = {}
        try:
            for name in ("checkout-healthy", "checkout-defect", "enterprise-evaluation"):
                document = (PAGES / f"{name}.html").read_text(encoding="utf-8")
                document = document.replace(
                    "https://production.invalid", f"http://127.0.0.1:{sentinel.server_port}"
                )
                request = AssessmentRequest(
                    url="https://synthetic.example/" + name,
                    mode="snapshot",
                    html=document,
                    categories=list(CATEGORIES),
                )
                id = service.submit(request)
                await service.tasks[id]
                report = service.report(id)
                reports[name] = report
                assert report["execution_status"] == "completed"
                assert report["acquisition"]["target_requests"] == 0
                incomplete_ids = {
                    check["id"] for check in report["checks"] if check["status"] == "incomplete"
                }
                # axe-core can require manual review even when its scan completes.
                assert incomplete_ids <= {"accessibility.axe"}
                assert not any(check["id"].endswith(".renderer") for check in report["checks"])
                assert len(report["evidence_files"]) == 3
                assert set(report["summary"]) == {"passed", "failed", "skipped", "incomplete"}
                assert set(report["scores"]["categories"]) == set(CATEGORIES)
                assert report["limitations"]
                archive = export_zip(service.path(id), report)
                with zipfile.ZipFile(BytesIO(archive)) as bundle:
                    names = set(bundle.namelist())
                    assert {"report.json", "report.md", "report.html"}.issubset(names)
                    assert set(report["evidence_files"]).issubset(names)
                    assert "index.html" not in names
                for issue in report["issues"]:
                    assert issue["severity"] and issue["evidence"]
                    assert issue["reproduction"] and issue["recommendation"]
                    for item in issue["evidence"]:
                        if item.endswith(".png"):
                            assert (service.path(id) / item).is_file()
            defect_ids = {item["id"] for item in reports["checkout-defect"]["issues"]}
            assert {
                "usability.title",
                "usability.heading",
                "accessibility.alt",
                "accessibility.labels",
                "responsiveness.viewport",
                "functionality.links",
                "responsiveness.width-360",
            }.issubset(defect_ids)
            assert (
                reports["checkout-healthy"]["scores"]["overall"]
                > reports["checkout-defect"]["scores"]["overall"]
            )
            (evidence_root / "pilot-review.json").write_text(
                json.dumps(
                    {
                        "scope": "three authored offline page states; not human or live-SPA validation",
                        "cases": {
                            name: {
                                "run_id": report["run_id"],
                                "score": report["scores"]["overall"],
                                "coverage": report["scores"]["coverage"],
                                "summary": report["summary"],
                                "issues": [issue["id"] for issue in report["issues"]],
                            }
                            for name, report in reports.items()
                        },
                        "target_requests": 0,
                        "human_churn_claim": False,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        finally:
            await service.close()

    try:
        asyncio.run(run())
    finally:
        sentinel.shutdown()
        sentinel.server_close()
        thread.join(timeout=5)
    assert contacts == []
