"""Lightweight local setup and diagnostics. Never starts browsers or downloads models."""

from __future__ import annotations

import importlib.metadata
import os
import shutil
import tempfile
from pathlib import Path

from frictionlab.configuration import ASSET_ROOT, CONFIG_DIRECTORY, ROOT, read_json
from frictionlab.planning.contracts import PlannerStopped
from frictionlab.planning.inference import InferenceSettings, load_inference, provider_key


def initialize(directory):
    directory = Path(directory).resolve()
    if directory.exists() and any(directory.iterdir()):
        raise ValueError("Workspace already has configuration; init never overwrites it")
    directory.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ASSET_ROOT / "configs", directory / "configs")
    (directory / "frictionlab.local.json").write_text(
        InferenceSettings().model_dump_json(indent=2), encoding="utf-8"
    )
    (directory / ".gitignore").write_text(
        "frictionlab.local.json\n.env*\nartifacts/\n.runtime/\nmodels/\n", encoding="utf-8"
    )
    for name in ("site", "examples/phase9-static"):
        shutil.copytree(ASSET_ROOT / name, directory / name, dirs_exist_ok=True)
    for name in (
        "README.md",
        "LICENSE",
        "SECURITY.md",
        "CONTRIBUTING.md",
        "IMPLEMENTATION_PLAN.md",
    ):
        shutil.copy2(ASSET_ROOT / name, directory / name)
    shutil.copytree(ASSET_ROOT / "docs", directory / "docs", dirs_exist_ok=True)
    return {
        "workspace": str(directory),
        "provider": "local",
        "downloads": False,
        "next": "Set FRICTIONLAB_HOME to this directory, then run frictionlab doctor",
    }


def doctor(inference_path=None):
    checks = []

    def check(name, ok, detail):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    try:
        ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=ROOT):
            pass
        check("workspace_writable", True, str(ROOT))
    except OSError:
        check("workspace_writable", False, "Choose a writable FRICTIONLAB_HOME")
    from frictionlab.assessment.render import browser_path

    browser = browser_path()
    check(
        "browser",
        browser and Path(browser).is_file(),
        "Use FRICTIONLAB_BROWSER_PATH for your installed Chromium/Chrome",
    )
    for package in ("playwright", "browser-use", "smolagents", "duckdb", "httpx"):
        try:
            check(package, True, importlib.metadata.version(package))
        except importlib.metadata.PackageNotFoundError:
            check(package, False, "Install locked project dependencies")
    try:
        settings = load_inference(inference_path)
        check("inference_policy", True, settings.provider)
        if settings.provider != "local":
            provider_key(settings.provider)
            check("provider_key", True, "Present; value never printed; live API not checked")
        else:
            manifest = read_json(CONFIG_DIRECTORY / "resource-manifest.json")
            key = "runtime" if os.name == "nt" else "runtime_linux"
            available = all(
                (ROOT / manifest[item]["local_path"].replace("\\", "/")).is_file()
                for item in (key, "model")
            )
            check(
                "local_model_resources",
                available,
                "Existence only; checksum verified at startup; BYOK avoids weight download",
            )
    except (PlannerStopped, ValueError, OSError):
        check(
            "inference_policy", False, "Missing key or invalid configuration; see local setup guide"
        )
    assessment_required = {"workspace_writable", "playwright", "httpx"}
    ready_for_assessment = all(
        item["ok"] for item in checks if item["check"] in assessment_required
    ) and assessment_required.issubset({item["check"] for item in checks})
    return {
        "ready_for_audit": all(item["ok"] for item in checks),
        "ready_for_assessment": ready_for_assessment,
        "ready_for_offline_browser": ready_for_assessment and bool(browser),
        "checks": checks,
        "network_requests": 0,
        "downloads": False,
        "models_started": False,
    }


async def provider_check(model: str):
    """One explicitly requested, bounded Morpheus inference; return no model text or key."""
    import asyncio
    import time

    from frictionlab.planning.cloud_transport import CloudModelRuntime

    settings = InferenceSettings(
        provider="morpheus",
        model=model,
        allow_remote=True,
        share_sanitized_state=True,
        billing_acknowledged=True,
        max_requests=1,
        max_tokens=4096,
        max_runtime_seconds=20,
        request_timeout_seconds=15,
        max_retries=0,
    )
    runtime = CloudModelRuntime(settings)
    try:
        await runtime.__aenter__()
        response = await asyncio.to_thread(
            runtime.complete,
            [
                {"role": "system", "content": 'Return only JSON: {"ok": true}.'},
                {"role": "user", "content": "Connection check."},
            ],
            32,
            time.monotonic() + 15,
        )
        message = response["choices"][0]["message"]["content"]
        return {
            "connected": isinstance(message, str) and bool(message),
            "provider": "morpheus",
            "model": model,
            "requests": runtime.budget.requests,
            "model_text_saved": False,
        }
    except PlannerStopped as exc:
        return {
            "connected": False,
            "provider": "morpheus",
            "category": exc.category,
            "requests": runtime.budget.requests,
            "model_text_saved": False,
        }
    finally:
        await runtime.close()
