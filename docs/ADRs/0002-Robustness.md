Kaizen Robustness Roadmap.md
Phase 1 — Foundation (Week 1–2)

✅ ADR 0002 accepted.

Implement minimal interfaces + Pydantic schemas for:

ActionDTO <sub>(resolved action)</sub>

SnapshotPayload <sub>(DOM + PNG metadata)</sub>

TestResultDTO

Add config constants (VISUAL_TOLERANCE, HEALER_DEPTH, etc.) in settings.py.

Introduce structured logging (JSON lines with run_id, step_id).

Extend pre-commit with bandit (security linting).

Write unit tests for schemas + log format → commit: test(core): schema and logging validation.

Phase 2 — Snapshot MVP (Week 3–4)

Implement snapshot_runner.py with minimal payload + thresholds (0.25 % pixel tolerance).

Store snapshots to filesystem under snapshots/{suite}/{test}/.

Add reporter.py (JSON + HTML summary).

Commit: feat(engine): snapshot runner MVP.

Phase 3 — Healer & Resolver (Week 5–6)

Introduce element fingerprints (weighted text/tag/position).

Implement selector_healer.py with 2-step depth + LLM fallback.

Add unit + chaos tests (broken selectors).

Commit: feat(engine): selector healer with fingerprint matching.

Phase 4 — Observability (Week 7)

Aggregate run metrics: execution time, heal success rate, diff percent.

Expose via reporter.py and structured logs.

Plan Prometheus integration (later).

Commit: feat(engine): structured metrics logging.

Phase 5 — CI/CD & Security (Week 8)

Jenkins pipeline matrix (lint → unit → e2e → artifact upload).

Add SBOM generation (cyclonedx-py).

Ensure Docker runs non-root and passes secret scan.

Commit: ci(jenkins): secure artifact pipeline.

Phase 6 — Learning Loop (Future Q2)

Persist heal attempt history → adjust weights over time.

Add LLM adapter interface so models can be swapped (Ollama/OpenAI/local).

Introduce config profiles (local, ci, cloud).

Commit: feat(core): adaptive healer weights.
