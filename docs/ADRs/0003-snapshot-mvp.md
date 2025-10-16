# ADR 0002 — Snapshot MVP & E2E Smoke

- **Status:** Accepted
- **Date:** 2025-10-16
- **Owners:** Kaizen Engine Team
- **Related:** ADR-0001 (Monorepo)

## Context

We have a working engine in **Snapshot** and **Live** modes (Python 3.11, **FastAPI** – web API, **Playwright** – browser automation, **Pydantic v2** – runtime config/validation, **Dependency Injector** – **DI** wiring, **pytest** – tests). We need a minimal, deterministic Snapshot flow that persists artifacts, plus a lightweight **E2E** _(end-to-end)_ smoke in **CI/CD** to detect regressions early.

## Decision

1. **Snapshot MVP** writes deterministic artifacts to `snapshots/{suite}/{test}/`:
   - `input.html` (if provided)
   - `page.png` (final screenshot if available)
   - `steps.jsonl` (**JSONL** – newline-delimited JSON logs per step)
   - `resolve.json` (final locator summary)
2. Introduce two tunables in config:
   - `VISUAL_TOLERANCE = 0.0025` (0.25%)
   - `HEALER_DEPTH = 2`
3. Add **E2E smoke** (snapshot + live) to pipeline after unit tests; archive `snapshots/**` and `logs/**`.

## Rationale

- Deterministic, file-system artifacts simplify debugging and regressions.
- Small tunables keep behavior stable while allowing later tuning.
- A fast **E2E** smoke increases confidence without slowing CI.

## Consequences

- Quick feedback loop; simple to inspect locally and in CI artifacts.
- HTML reports and richer analytics deferred to a later ADR/phase.

## Alternatives (rejected for now)

- Full HTML report + dashboards now → too big for Step 10.
- Heavier healing or ML scoring → postpone for robustness phases.

## Implementation Plan (tiny steps)

- [ ] Add settings (`VISUAL_TOLERANCE`, `HEALER_DEPTH`) via **Pydantic v2** settings.
- [ ] Add `JsonlLogger` (structured **JSONL** writer) and wire via **DI**.
- [ ] Persist Snapshot artifacts in runner.
- [ ] Add E2E smoke: minimal `smoke.html`, two simple specs, two pytest checks.
- [ ] Makefile targets: `e2e-snapshot`, `e2e-live`, `e2e`.
- [ ] Jenkins stage `e2e-smoke` that runs `make e2e` and archives artifacts.

## Rollback

Revert the stage and logger wiring; Snapshot MVP is additive and isolated.
