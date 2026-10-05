# Local replica preparation and Morpheus qualification

Phases 15–16 stay on the operator's computer. The existing GitHub Pages landing site does not run assessments or store reports. Supabase is not used.

## Replica preparation

The interactive agent currently runs only on its bundled, disposable fixture. A local source directory or a `staging` URL is not proof that a backend, database or third-party integrations are isolated. Prepare a JSON declaration such as:

```json
{
  "app_origin": "http://127.0.0.1:3000",
  "source_directory": "C:/path/to/disposable-copy",
  "build_id": "local-test-build",
  "disposable_data": true,
  "synthetic_accounts": true,
  "mocked_integrations": true,
  "production_origins": ["https://production.example"],
  "network_boundary": "Document the separate egress-deny boundary",
  "cleanup_plan": "Document owned database and artifact cleanup"
}
```

Run `uv run frictionlab replica-check path/to/manifest.json`. The command reads local metadata only and makes zero target requests. It deliberately reports `execution_enabled: false` even if every field is filled: those declarations cannot prove the independent network boundary or backend isolation. The existing bundled-fixture cohort remains the only interactive execution target. Do not run agents against a deployed product or ordinary staging server.

## Morpheus key and model

Morpheus is an optional OpenAI-compatible provider at the fixed `https://api.mor.org/api/v1` endpoint. An ignored local `.env` can contain `MORPHEUS_API_KEY` and `MORPHEUS_BASE_URL`; the app reads only these named entries and never sends the key to its dashboard clients. The native OS credential store or session-only entry remains preferable when sharing a workspace. A `.env` file is plaintext, even when Git-ignored; do not commit, upload or paste it into reports.

Select Morpheus, an available model, redacted-findings consent and the paid-credit acknowledgement in the desktop/dashboard. Choose **Use ignored local .env key** if using that file. For CLI setup, run `uv run frictionlab configure --provider morpheus --model MODEL_ID --share-findings --billing-acknowledged --use-local-env`. The report sends a maximum of one bounded AI recommendation request when enabled and failed checks exist; provider failure leaves deterministic findings intact. Morpheus pricing and credit availability vary by model/account. No paid fallback is started automatically, but a permitted request may consume your own credits.

An explicit connection smoke is `uv run frictionlab provider-check --model MODEL_ID --billing-acknowledged`. It makes at most one inference request and prints only connection status/category/request count, not the response or key. Do not repeat it casually because it may consume credits. URL-only/offline structural assessment needs no AI key.

Phase 15 external-replica execution remains a separate qualification after a permissioned local app copy and independently verified data/network boundary are available. No external replica was supplied for the current fixture-only gate.
