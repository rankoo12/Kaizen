# ADR 0004: Observability & Metrics

**Date:** 2025-10-19
**Status:** Proposed
**Authors:** Ran Eckstein

---

## 🎯 Context

The Kaizen Engine MVP now runs fully inside a reproducible CI/CD environment (Docker + Makefile + Jenkins).
The next step is to make the system _observable_ — so we can understand **what the engine does, how long it takes, and how well it performs** without reading raw logs.

Observability means exposing runtime signals (metrics, logs, traces) that let us answer questions like:

- How many steps succeeded vs. failed in a given run?
- What is the average healing success rate?
- How long does a full suite or a single step take?
- Are diffs increasing over time?
- Which tests are the slowest or most brittle?

---

## 🧩 Decision

We will introduce a lightweight **Observability & Metrics Layer** within the Engine, composed of:

1. **Reporter Hooks (already defined in `IReporter`)**

   - Extend `on_step()` and `on_finish()` hooks to collect timing, result, and diff statistics.
   - All step runs will emit structured `StepRun` JSON entries containing metrics such as:
     ```json
     {
       "step": "click login",
       "status": "passed",
       "duration_ms": 1200,
       "heal_attempts": 1,
       "diff_percent": 0.004
     }
     ```

2. **Run-level Aggregation**

   - Each `Runner` (Snapshot/Live) will aggregate metrics into a `RunMetrics` summary object:
     ```python
     class RunMetrics(BaseModel):
         total_steps: int
         passed: int
         failed: int
         heal_success_rate: float
         avg_duration_ms: float
         max_diff_percent: float
     ```
   - The summary will be persisted in `logs/{run_id}.metrics.json`.

3. **/api/metrics Endpoint**

   - Add a FastAPI route `/api/metrics` returning aggregated results.
   - Later phases can expose these as **Prometheus metrics** (e.g. `/metrics`).

4. **JSONL Logs as the Ground Truth**
   - Structured JSONL (`logs/{run_id}.jsonl`) remains the raw source of truth.
   - Aggregations will be derived from it for quick queries.

---

## 🧱 Implementation Outline

| Component                       | Responsibility                       |
| ------------------------------- | ------------------------------------ |
| `IReporter` / `StepRun`         | Extend with time/diff/heal counters  |
| `RunMetrics`                    | Aggregate step-level data            |
| `Reporter`                      | Persist `.metrics.json` summaries    |
| `FastAPI /metrics route`        | Serve metrics to CI dashboards       |
| (Optional) `PrometheusExporter` | Convert metrics to Prometheus format |

**Data Flow**

```mermaid
flowchart LR
  Runner --> Reporter --> JSONL[JSONL Logs]
  JSONL --> Metrics[RunMetrics Aggregator]
  Metrics --> API[/api/metrics]
  API --> Grafana[(Grafana Dashboard)]
```
