"""Local, fixture-only agent jobs shared by the CLI and desktop dashboard."""

from __future__ import annotations

import asyncio
import io
import json
import os
import re
import uuid
import zipfile
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from frictionlab.assessment.render import browser_path
from frictionlab.assessment.service import read_settings
from frictionlab.configuration import CONFIG_DIRECTORY, ROOT, read_json, resolve_run
from frictionlab.contracts.models import ExecutionStatus, ReportStatus, RunReport
from frictionlab.credentials import get_key
from frictionlab.planning.contracts import load_limits
from frictionlab.planning.runner import run_persona
from frictionlab.reporting import unexecuted_report, write_report


class AgentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    persona: Literal["impatient_mobile", "keyboard_low_vision", "enterprise_evaluator"]
    journey: Literal["checkout_review", "delivery_information", "keyboard_checkout"]
    variant: Literal[
        "healthy", "generic_validation", "dead_button", "delayed_feedback",
        "hidden_shipping", "focus_trap",
    ] = "healthy"
    max_requests: int = Field(default=8, ge=1, le=12, strict=True)
    max_runtime_seconds: int = Field(default=120, ge=30, le=240, strict=True)
    account_usage_acknowledged: bool = False


class AgentWorkspace:
    def __init__(self, root: Path):
        self.root = Path(root) / "agent-runs"
        self.root.mkdir(parents=True, exist_ok=True)
        self.tasks: dict[str, asyncio.Task] = {}
        self.semaphore = asyncio.Semaphore(1)
        self.recover()

    def path(self, id: str) -> Path:
        if str(uuid.UUID(id)) != id:
            raise ValueError("Invalid agent run identifier")
        return self.root / id

    def progress(self, id: str, status: str, stage: str) -> dict:
        value = {"id": id, "status": status, "stage": stage}
        destination = self.path(id) / "progress.json"
        temporary = destination.with_suffix(".tmp")
        temporary.write_text(json.dumps(value), encoding="utf-8")
        temporary.replace(destination)
        return value

    def status(self, id: str) -> dict:
        return json.loads((self.path(id) / "progress.json").read_text(encoding="utf-8"))

    def report(self, id: str) -> dict:
        return json.loads((self.path(id) / "report.json").read_text(encoding="utf-8"))

    def evidence_path(self, id: str, name: str) -> Path:
        allowed = {item["path"] for item in self.report(id)["visual_evidence"]}
        if (
            name not in allowed
            or not re.fullmatch(r"evidence/[A-Za-z0-9._/-]+\.png", name)
            or ".." in Path(name).parts
        ):
            raise ValueError("Evidence is not listed in this report")
        destination = (self.path(id) / name).resolve()
        if not destination.is_relative_to(self.path(id).resolve()) or not destination.is_file():
            raise ValueError("Evidence file is unavailable")
        return destination

    def export_zip(self, id: str) -> bytes:
        report = self.report(id)
        references = list(report["visual_evidence"])
        for key in ("trajectories", "friction_events"):
            for item in report[key]:
                references.extend(item.get("evidence", []))
        if report.get("abandonment_diagnosis"):
            references.extend(report["abandonment_diagnosis"]["evidence"])
        paths = []
        for name in sorted({item["path"] for item in references}):
            destination = (self.path(id) / name).resolve()
            if (
                not re.fullmatch(r"evidence/[A-Za-z0-9._/-]+\.(png|svg|json|txt)", name)
                or ".." in Path(name).parts
                or not destination.is_relative_to(self.path(id).resolve())
                or not destination.is_file()
            ):
                raise ValueError("A reported evidence file is missing or invalid; export stopped")
            paths.append((destination, name))
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for format in ("json", "md", "html"):
                path = self.path(id) / ("report." + format)
                archive.write(path, path.name)
            for destination, name in paths:
                archive.write(destination, name)
        return output.getvalue()

    def list(self) -> list[dict]:
        entries = sorted(self.root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
        result = []
        for entry in entries[:100]:
            try:
                result.append(self.status(entry.name))
            except (OSError, ValueError):
                continue
        return result

    def readiness(self) -> dict:
        settings = read_settings(self.root.parent)
        browser = browser_path()
        gaps = []
        if not browser:
            gaps.append("Install Chrome/Edge/Chromium or set FRICTIONLAB_BROWSER_PATH.")
        if settings.provider == "local":
            resources = self.local_resources()
            if settings.model != resources["model"]:
                gaps.append("Explicitly select the prepared local planner in this workspace first.")
            if not resources["available"]:
                gaps.append("Connect a BYOK provider or explicitly prepare the pinned local runtime and model; no downloads are automatic.")
        elif not get_key(settings.provider):
            gaps.append("Connect the selected provider key in this local workspace.")
        return {
            "target": "bundled_disposable_fixture_only",
            "browser_available": bool(browser),
            "provider": settings.provider,
            "model": settings.model,
            "planner_contract": "restricted local choice adapter" if settings.provider == "local" else "bounded JSON action adapter",
            "capability_verified": False,
            "local_resources": self.local_resources(),
            "ready_to_attempt": not gaps,
            "gaps": gaps,
            "external_replica_enabled": False,
            "network_requests": 0,
        }

    def local_resources(self) -> dict:
        """Existence-only preflight. Runtime verifies the pinned weight hash before launch."""
        manifest = read_json(CONFIG_DIRECTORY / "resource-manifest.json")
        runtime_key = "runtime" if os.name == "nt" else "runtime_linux"
        paths = [
            (ROOT / manifest[key]["local_path"].replace("\\", "/")).resolve()
            for key in (runtime_key, "model")
        ]
        return {
            "available": all(path.is_file() for path in paths),
            "integrity_verified": False,
            "downloads_started": False,
            "model": "Qwen3-4B-Q4_K_M",
            "note": "Optional resources require explicit setup. Weight integrity is checked before launch; readiness does not prove planning capability.",
        }

    def blocked(
        self, id: str, reason: str, *, terminal_status: ExecutionStatus = ExecutionStatus.BLOCKED
    ) -> None:
        report = unexecuted_report(
            reason,
            execution_status=terminal_status,
        ).model_copy(update={"run_id": uuid.UUID(id)})
        write_report(report, self.root, prepared_directory=True, output_directory=self.path(id))
        self.progress(id, str(terminal_status), reason)

    def retain_terminal(self, id: str, status: ExecutionStatus, reason: str) -> None:
        report = RunReport.model_validate(self.report(id))
        # A completed report may have been saved just before cancellation or process exit.
        if report.execution_status == ExecutionStatus.COMPLETED:
            self.progress(id, str(report.execution_status), "Completed report retained")
            return
        report = report.model_copy(update={
            "execution_status": status,
            "report_status": ReportStatus.PARTIAL,
            "terminal_reason": reason,
        })
        write_report(
            report, self.root, prepared_directory=True, replace_existing=True,
            output_directory=self.path(id),
        )
        self.progress(id, str(status), reason)

    def submit(self, request: AgentRequest) -> str:
        if sum(not task.done() for task in self.tasks.values()) >= 2:
            raise ValueError("Agent queue is full")
        id = str(uuid.uuid4())
        self.path(id).mkdir()
        ready = self.readiness()
        if not ready["ready_to_attempt"]:
            self.blocked(id, " ".join(ready["gaps"]))
            return id
        settings = read_settings(self.root.parent)
        if settings.provider == "morpheus" and not request.account_usage_acknowledged:
            self.blocked(id, "Acknowledge this run's potential Morpheus charges before starting.")
            return id
        self.progress(id, "queued", "Waiting for the local agent worker")
        self.tasks[id] = asyncio.create_task(self.execute(id, request, settings))
        return id

    async def execute(self, id: str, request: AgentRequest, settings) -> None:
        try:
            async with self.semaphore:
                self.progress(id, "running", "Model-selected actions on bundled fixture")
                configuration = read_json(CONFIG_DIRECTORY / "run.example.json")
                configuration["id"] = id
                resolved = resolve_run(configuration)
                limits = load_limits().model_copy(
                    update={
                        "max_runtime_seconds": request.max_runtime_seconds,
                        "max_steps": request.max_requests,
                        "max_tool_calls": request.max_requests,
                    }
                )
                bounded = settings.model_copy(
                    update={
                        "max_requests": request.max_requests,
                        "max_tokens": min(120000, request.max_requests * 10000),
                        "max_runtime_seconds": request.max_runtime_seconds,
                        "max_retries": 0,
                    }
                )
                broker = await run_persona(
                    resolved,
                    persona_id=request.persona,
                    journey_id=request.journey,
                    variant=request.variant,
                    behavioral=True,
                    artifact_root=self.root,
                    session_id=id,
                    limits=limits,
                    inference=bounded,
                )
                self.progress(id, str(broker.report.execution_status), "Report and evidence saved")
        except asyncio.CancelledError:
            if (self.path(id) / "report.json").is_file():
                self.retain_terminal(id, ExecutionStatus.CANCELLED, "Partial report retained after cancellation")
            else:
                self.blocked(
                    id,
                    "Agent was cancelled before browser evidence was saved.",
                    terminal_status=ExecutionStatus.CANCELLED,
                )
        except Exception as exc:  # noqa: BLE001 -- terminal jobs must retain a report
            if (self.path(id) / "report.json").is_file():
                self.retain_terminal(id, ExecutionStatus.FAILED, f"Agent stopped ({type(exc).__name__}); report retained")
            else:
                self.blocked(id, f"Agent failed before execution ({type(exc).__name__}).")

    def cancel(self, id: str) -> None:
        task = self.tasks.get(id)
        if not task or task.done():
            raise ValueError("Agent run is no longer active")
        task.cancel()

    def recover(self) -> None:
        for entry in self.root.iterdir():
            if not entry.is_dir():
                continue
            try:
                state = self.status(entry.name)
                if state["status"] in {"queued", "running"}:
                    if (entry / "report.json").is_file():
                        self.retain_terminal(entry.name, ExecutionStatus.INTERRUPTED, "Saved report retained after restart")
                    else:
                        self.blocked(
                            entry.name,
                            "Application stopped before agent evidence was saved.",
                            terminal_status=ExecutionStatus.INTERRUPTED,
                        )
            except (OSError, ValueError, KeyError):
                continue

    async def close(self) -> None:
        pending = [task for task in self.tasks.values() if not task.done()]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
