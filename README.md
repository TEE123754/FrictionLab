# FrictionLab

**Evidence-led website quality assessment and synthetic user testing, on your own machine.**

FrictionLab helps product, design and engineering teams investigate interface problems before release. Assess an offline website copy, run controlled synthetic journeys on the bundled test application, and review findings with saved evidence and practical recommendations.

The open-source application runs locally through a CLI or Windows desktop launcher. Reports remain on your computer. Optional cloud AI uses your own provider account; no hosted FrictionLab backend is required.

[Implementation plan](IMPLEMENTATION_PLAN.md) · [Verified progress](docs/phase-status.md) · [Sample report](examples/phase9-static/index.html) · [Downloads](https://github.com/TEE123754/FrictionLab/releases/tag/v0.1.0)

## Product capabilities

- **Six assessment categories:** functionality, usability, accessibility, responsiveness, performance and security, with explicit limits for each evidence source.
- **Synthetic browser journeys:** select a persona, goal and seeded interface variant on a disposable local storefront. AI chooses actions through a restricted browser broker.
- **Reviewable results:** severity-ranked findings, supporting evidence, reproduction or verification guidance, remediation advice and visible coverage gaps.
- **Local workspace:** progress, stop controls, saved history, screenshots and JSON, Markdown, offline HTML and ZIP exports.
- **Controlled inference:** explicit input-sharing consent, request and runtime limits, provider failure reporting and optional local inference.

**Current scope:** autonomous execution accepts bundled fixtures only. User-supplied repositories and isolated application replicas remain under development and are blocked from interactive execution. Synthetic abandonment is a UX hypothesis, not a prediction of human conversion or churn. A successful API connection does not establish browser-planning capability.

## Get started

Use Python 3.12 and [uv](https://github.com/astral-sh/uv). The latest local workflow is on the development branch:

```sh
git clone --branch codex/phase17-local-readiness https://github.com/TEE123754/FrictionLab.git
cd FrictionLab
uv sync --locked
uv run frictionlab doctor --assessment-only
uv run frictionlab start
```

Open the localhost dashboard shown by the CLI. For static assessment, paste a URL, supply an offline HTML or ZIP copy, choose individual categories or all checks, and start. A URL alone provides very limited evidence. Core static checks do not require an AI key.

For a synthetic journey, connect your provider in the dashboard, choose a bundled persona and goal, set decision/time limits, authorize the run and start. Review the terminal reason, findings, timeline and screenshots before exporting. Existing Chrome, Edge or Chromium is required for browser inspection; browsers and model weights are never downloaded automatically.

To open the native launcher from source:

```sh
uv run frictionlab desktop
```

The launcher provides masked API-key entry and start/open/stop controls for the same local dashboard.

### Windows download

[Download the v0.1.0 release and checksums](https://github.com/TEE123754/FrictionLab/releases/tag/v0.1.0), extract the Windows ZIP and open `FrictionLab.exe`. This earlier release supports offline assessment; it **predates the new synthetic-agent panel and local-planner selector**. Current development binaries are retained temporarily in GitHub Actions artifacts, not published as a new release. Source installation above provides the current workflow.

See the [installation and scope guide](docs/local-assessment.md) and [pilot/readiness guide](docs/phase17-release-readiness.md).

## Protecting the website under review

**Browser isolation alone does not prevent production side effects.** Live requests can create logs, trigger analytics or alter backend state. FrictionLab does not automatically visit or crawl your submitted website URL.

| Input or mode | Available checks | Boundary and limitations |
|---|---|---|
| URL text | URL scheme and declared target information | No DNS lookup or target request. Most checks are skipped. |
| Uploaded offline HTML/ZIP | Structure, labels, axe accessibility, static viewport checks and HTML-size heuristics | Rendered at a synthetic origin with website scripts, forms, frames and external traffic blocked. Cannot establish dynamic functionality. |
| Explicit public capture | One public HTML response and selected original headers | One approved GET, without authentication, redirects or subresources. A GET can have side effects; this is not zero-contact testing. |
| Bundled disposable fixture | Bounded model-driven goals, observed friction, patience and synthetic abandonment | Synthetic data and controlled integrations; no arbitrary website navigation. |
| User-supplied application | Planned interactive journeys | Requires verified separate data, mocked integrations, an independent network boundary and additional access. Currently blocked. |

Offline assessment cannot establish backend transactions, real performance/Core Web Vitals, complete assistive usability, authorization correctness or exploit resistance. These require a controlled replica, source code and/or additional access. Unsupported checks are skipped; interrupted or unavailable checks are incomplete. Recommendations do not edit source or deploy fixes.

## Reports that support decisions

Static assessment reports include overall and category scores, executed coverage, confidence, severity-ranked issues, evidence, reproduction steps and remediation guidance. They account for passed, failed, skipped and incomplete checks.

Agent reports include the goal and persona scope, completion or terminal reason, action history, model outcomes, application friction, patience changes, screenshots, findings and limitations. Model failures are kept separate from observed application problems; a blocked run is never presented as a completed website audit. Agent reports are not a substitute for the six-category static scorecard.

ZIP exports contain the report and its referenced evidence. Review supplied content and screenshots before sharing. Scores describe executed checks and are not certification or proof of release readiness.

## AI configuration, privacy and cost

Supported remote adapters are Groq, Gemini and Morpheus. Connect keys inside the local app. Remembered keys use the native OS credential store when available; otherwise use session memory. An operator-requested ignored `.env` is a plaintext exception. Never commit keys or include them in an issue or report.

Remote inference sends opted-in, bounded, sanitized observations or findings to the selected provider. Sanitization does not guarantee that all supplied content is non-sensitive. Provider availability, model compatibility and free-tier quotas vary. **Morpheus may charge usage** and requires separate acknowledgement; the tool does not guarantee zero-cost inference or silently fall back to another provider.

A prepared local llama.cpp/Qwen3 planner can be explicitly selected in the dashboard. Setup is optional, requires about 2.5 GB of weights plus memory/CPU, and is documented in the [local installation guide](docs/phase10-installation.md). Selection performs no download or model launch. The pinned weight hash is checked before execution; file presence alone does not establish planner capability.

## Technology

| Layer | Tools | Purpose |
|---|---|---|
| Browser | [Playwright Python](https://github.com/microsoft/playwright-python), [browser-use](https://github.com/browser-use/browser-use) | Chromium automation and semantic grounding |
| Agents | [smolagents](https://github.com/huggingface/smolagents), Pydantic | Restricted planning tools, action validation and execution budgets |
| Local inference | [llama.cpp](https://github.com/ggml-org/llama.cpp), [Qwen3 GGUF](https://huggingface.co/Qwen/Qwen3-4B-GGUF) | Optional CPU planner |
| Local service | FastAPI, uvicorn, HTTPX | Authenticated loopback dashboard and bounded provider transport |
| Evidence | DuckDB, OpenTelemetry | Local cohort records and traces |
| Review | HTML/CSS/JavaScript; optional Streamlit/Plotly | Assessment workspace and cohort analysis |
| Desktop | Tkinter, keyring, PyInstaller | Native launcher, credential storage and Windows packaging |
| Evaluation | Owned fixtures, [Mind2Web](https://huggingface.co/datasets/osunlp/Mind2Web) | Controlled acceptance and reference diagnostics |

Vision models and Phoenix are optional integrations, not prerequisites for the current assessment workflow. Dependencies, models and datasets retain their own licenses.

## Project status and contribution

The offline assessment, Windows launcher and bundled-fixture execution/export milestones have acceptance evidence in the [implementation plan](IMPLEMENTATION_PLAN.md). External replica preparation, real-model qualification of the new dashboard path and broader interactive pilots remain open. Hosted deployment is the final deferred phase; Supabase is not required for local use.

Acceptance runs after construction, with affected checks repeated only when a repair warrants it. See [CONTRIBUTING](CONTRIBUTING.md) for development and [SECURITY](SECURITY.md) for vulnerability reporting. FrictionLab is licensed under [MIT](LICENSE).
