"""The local declaration cannot become execution authorization."""

import json

from frictionlab.replica_preflight import inspect_declaration


def test_complete_external_declaration_is_still_blocked_without_contact(tmp_path):
    source = tmp_path / "copy"
    source.mkdir()
    manifest = tmp_path / "replica.json"
    manifest.write_text(
        json.dumps(
            {
                "app_origin": "http://127.0.0.1:3000",
                "source_directory": str(source),
                "build_id": "owned-copy",
                "disposable_data": True,
                "synthetic_accounts": True,
                "mocked_integrations": True,
                "production_origins": ["https://production.example"],
                "network_boundary": "separate deny-all egress container",
                "cleanup_plan": "destroy copied database",
            }
        ),
        encoding="utf-8",
    )
    result = inspect_declaration(manifest)
    assert result["execution_enabled"] is False
    assert result["target_requests"] == 0
    assert len(result["gaps"]) == 1
    assert "cannot prove" in result["gaps"][0]


def test_missing_isolation_prerequisites_are_named_without_navigation(tmp_path):
    manifest = tmp_path / "replica.json"
    manifest.write_text(
        json.dumps(
            {
                "app_origin": "https://staging.example.com",
                "source_directory": str(tmp_path / "missing"),
                "build_id": "claimed-staging",
            }
        ),
        encoding="utf-8",
    )
    result = inspect_declaration(manifest)
    assert result["execution_enabled"] is False
    assert result["target_requests"] == 0
    assert len(result["gaps"]) >= 8
