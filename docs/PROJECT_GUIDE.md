# Project Guide

This guide summarizes the vision, principles, layout, and core contracts for Kaizen. It reflects current decisions (Postgres-first storage and a thin Portal backend) and links to ADRs for context.

## 1) Vision & Scope
- Kaizen turns plain‑English steps (e.g., "Open google.com", "Click Login") into executable and reliable browser tests for sites the system has never seen.
- Deployables:
  - Engine (program): plans and executes steps via Playwright, resolves elements (semantic + optional visual), captures artifacts, learns stable selectors.
  - Portal (website): thin backend + minimal UI to author runs, launch them, and review results and metrics.
- Local‑first by default (open models via Ollama). Cloud/SaaS later.
- Deterministic and safe: JSON‑schema validation, visibility/uniqueness checks, conservative click policy.

## 2) Core Principles
- SOLID across modules; clear separation of concerns.
- Tool‑driven LLM: planner returns a JSON plan from a small Action Ontology (no phrase hardcoding).
- Engine ↔ Portal boundary via DTOs/OpenAPI; browser automation isolated behind `IBrowser`.
- Security by default: zero secrets in Git, non‑root containers, strict validation, guardrails for live actions.
- Ping‑pong iteration: build in small steps that are testable, reviewable, and CI‑verified.

## 3) Monorepo Decision (ADR‑0001)
- Monorepo with bounded contexts: `engine/`, `portal/`, `infra/`, `docs/`.
- Split later when release cadence or access controls diverge. Maintain versioned OpenAPI/DTOs to make splitting low‑friction.

## 4) Repository Layout (implemented)
- `engine/`: API (FastAPI), orchestrator, commands, resolving, browser adapters (Playwright first), healing, reporting, storage (Postgres‑first), config, tests.
- `portal/`: backend (FastAPI) with thin HTML page; proxies to Engine for runs/queue/artifacts; NL run endpoint.
- `infra/`: docker‑compose, OTEL collector, Prometheus, Grafana, Jenkins.
- `docs/`: ADRs, security, contributing, observability, this guide.

## 5) Engine Contracts (high level)
- `IBrowser`: `open`, `click`, `type`, `press`, `screenshot`, `frames`, `evaluate`, `scroll`.
- `IElementResolver`: `(TargetQuery, PageSnapshot) -> LocatorCandidates`; strategies combine semantic/label/attributes/structure.
- `IActionHandler`: per‑tool executor (open/click/type/press/wait/assert*/custom).
- `IReporter`: step/run callbacks; emits metrics/traces.
- `IStorage`: runs/steps/suites/queue/profiles (Postgres‑first); artifacts remain on disk (S3/MinIO later).

### Action Ontology (MVP)
- `open(url)`
- `click(target)`
- `type(target, text, clear?)`
- `press(key)`
- `waitFor(target|url|state)`
- `assertVisible(target)`
- `assertText(target, expected, match = equals|contains|regex)`
- `assertUrl(expected, match)`
- `custom(script)` (sandboxed)

### Data Models (DTOs)
- `TestSpec { id, name, steps: StepSpec[], vars?, tags? }`
- `StepSpec { index?, text, timeout?, data? }`
- `ToolCall { tool, args, meta? }`
- `TargetQuery { text?, css?, hints?, scope? }`
- `LocatorCandidates { primary, fallbacks[], confidence, reason, bbox? }`
- `Run { id, testId, status, startedAt, finishedAt }`
- `StepRun { runId, stepIndex, toolCall, result, reason?, durationMs, evidence }`

## 6) Storage (Decision Update)
- Postgres‑first for core entities (runs, steps, suites, queue, selector profiles). In‑memory is kept for local/dev.
- Queue uses `FOR UPDATE SKIP LOCKED` for multi‑worker claims; stale running jobs can be re‑queued (lease timeout).
- Artifacts (logs, snapshots) stay on disk for now; object storage later.

## 7) Portal (Thin UI)
- Single backend that proxies to the Engine API for runs, queue, and artifacts.
- Minimal inline page to enqueue runs and poll status; a richer React/Next.js UI comes later.

## 8) Security
- Live `open()` is restricted by `ALLOWED_URL_SCHEMES`.
- Defaults: `data:` and `about:blank` only. To allow http(s) locally: `KAIZEN_ALLOWED_URL_SCHEMES=https:,http:,about:blank,data:`.

## 9) ADRs
- `docs/ADRs/0001-monorepo.md` (monorepo decision)
- `docs/ADRs/0003-snapshot-mvp.md` (snapshot MVP & E2E)
- `docs/ADRs/0005-portal-thin-ui.md` (portal thin UI)
- `docs/ADRs/0006-db-persistence-postgres.md` (Postgres‑first persistence)

## 10) Roadmap & Plan
- See `docs/KAIZEN_PLAN.md` for the live plan with status, DoD, and tests.

## 11) Planner LLM Offline Training Loop

The planner “Super Bot” relies on a stable QA intent corpus and a clean
export path. The recommended offline loop is:

1. Run live QA flows through the engine so `run-*.jsonl` logs contain
   `planner.step` events (this is already wired via `EngineOrchestrator`).
2. From the repo root, build datasets and training exports:

   ```bash
   python scripts/planner_offline_training_loop.py
   ```

   This writes the following under `reports/`:
   - `planner_qa_dataset.jsonl` (raw examples from logs)
   - `planner_qa_train.jsonl` / `planner_qa_dev.jsonl` (curated splits)
   - `planner_qa_train_export.jsonl` / `planner_qa_dev_export.jsonl`
     (training-ready JSONL with `input`/`output`/`category`).

3. Use the `*_export.jsonl` files with your chosen LLM training stack
   (for example, fine-tuning a small model). Kaizen does not ship a
   trainer; this loop is intentionally backend-agnostic.
4. Point the engine at the tuned model via settings/ENV (for example,
   by changing the planner model name), then run:

   ```bash
   python scripts/eval_planner_ablation.py
   ```

   to compare tuned vs glue/LLM behavior on the same QA corpus.

All steps are deterministic and do not require secrets or external services
beyond whatever you choose for actual LLM training.
