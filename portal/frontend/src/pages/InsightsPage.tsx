import { useEffect, useMemo, useState } from "react";

type MetricsSummary = {
  metrics_schema?: number;
  healed_rate?: number;
  heal_attempts?: number;
  heal_successes?: number;
  average_duration?: number;
  runs_total?: number;
  runs_failed?: number;
  resolver_fallback_steps?: number;
  resolver_total_steps?: number;
};

type LearnedSelector = {
  query_text: string;
  primary_locator: string;
  confidence: number;
  times_used: number;
  last_seen_at: number | null;
};

type LearnedSelectorsResponse = {
  selectors?: LearnedSelector[];
};

type FlakyTest = {
  test_id: string;
  test_name?: string | null;
  flakiness_rate: number;
  recent_failures: number;
  last_failed_at: number | null;
};

type FlakyTestsResponse = {
  tests?: FlakyTest[];
};

const formatPercent = (value: number | null | undefined): string => {
  if (value == null || Number.isNaN(value)) return "—";
  const pct = value * (value <= 1 ? 100 : 1);
  return `${pct.toFixed(0)}%`;
};

const formatMillis = (seconds: number | null | undefined): string => {
  if (!seconds || !Number.isFinite(seconds)) return "—";
  const ms = seconds * 1000;
  if (ms < 1) return "< 1 ms";
  if (ms < 1000) return `${ms.toFixed(0)} ms`;
  const s = ms / 1000;
  return `${s.toFixed(1)} s`;
};

const formatDateShort = (ts?: number | null): string => {
  if (!ts || Number.isNaN(ts)) return "—";
  try {
    const d = new Date(ts * 1000);
    if (Number.isNaN(d.getTime())) return "—";
    return d.toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
    });
  } catch {
    return "—";
  }
};

export const InsightsPage = () => {
  const [metrics, setMetrics] = useState<MetricsSummary | null>(null);
  const [metricsError, setMetricsError] = useState<string | null>(null);
  const [selectors, setSelectors] = useState<LearnedSelector[]>([]);
  const [selectorsError, setSelectorsError] = useState<string | null>(null);
  const [flakyTests, setFlakyTests] = useState<FlakyTest[]>([]);
  const [flakyError, setFlakyError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const loadMetrics = async () => {
      try {
        const res = await fetch("/api/metrics/summary?window=50");
        if (!res.ok) {
          const text = await res.text();
          throw new Error(`Status ${res.status}: ${text}`);
        }
        const data: MetricsSummary = await res.json();
        if (!cancelled) {
          setMetrics(data);
          setMetricsError(null);
        }
      } catch (e) {
        if (!cancelled) {
          setMetricsError(
            e instanceof Error
              ? e.message
              : "Unable to load metrics summary.",
          );
        }
      }
    };

    const loadSelectors = async () => {
      try {
        const res = await fetch("/api/insights/selectors");
        if (!res.ok) {
          throw new Error(`Status ${res.status}`);
        }
        const data: LearnedSelectorsResponse = await res.json();
        if (!cancelled) {
          setSelectors(data.selectors || []);
          setSelectorsError(null);
        }
      } catch (e) {
        if (!cancelled) {
          setSelectorsError(
            e instanceof Error
              ? e.message
              : "Unable to load learned selectors.",
          );
        }
      }
    };

    const loadFlaky = async () => {
      try {
        const res = await fetch("/api/insights/flaky-tests");
        if (!res.ok) {
          throw new Error(`Status ${res.status}`);
        }
        const data: FlakyTestsResponse = await res.json();
        if (!cancelled) {
          setFlakyTests(data.tests || []);
          setFlakyError(null);
        }
      } catch (e) {
        if (!cancelled) {
          setFlakyError(
            e instanceof Error
              ? e.message
              : "Unable to load flaky tests.",
          );
        }
      }
    };

    loadMetrics();
    loadSelectors();
    loadFlaky();

    const id = window.setInterval(loadMetrics, 15000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  const windowRuns = metrics?.runs_total ?? null;
  const healingSuccessRate = metrics?.healed_rate ?? null;
  const avgResolveTime = metrics?.average_duration ?? null;
  const fallbackUsage =
    metrics && metrics.resolver_total_steps
      ? (metrics.resolver_fallback_steps || 0) /
        (metrics.resolver_total_steps || 1)
      : null;

  const flakyChartPoints = useMemo(() => {
    return flakyTests
      .slice()
      .sort((a, b) => (a.flakiness_rate < b.flakiness_rate ? 1 : -1))
      .slice(0, 8);
  }, [flakyTests]);

  const openGrafana = () => {
    window.open("http://localhost:3000", "_blank", "noopener,noreferrer");
  };

  return (
    <section className="kp-dashboard" aria-label="Insights">
      <div className="kp-dashboard-header-card">
        <div>
          <h1 className="kp-dashboard-title">Insights</h1>
          <p className="kp-dashboard-subtitle">
            Healing performance, learned selectors, and flaky tests.
          </p>
        </div>
        <button
          type="button"
          className="kp-btn kp-btn-secondary kp-card-action-btn"
          onClick={openGrafana}
        >
          Open Grafana
        </button>
      </div>

      <div className="kp-dashboard-grid">
        {/* Metrics cards */}
        <section className="kp-card" aria-label="Healing metrics">
          <h2 className="kp-card-title">Run Metrics</h2>
          <div className="kp-card-body kp-insights-grid">
            <div className="kp-insight">
              <div className="kp-insight-label">Healing Success Rate</div>
              <div className="kp-insight-value">
                {formatPercent(healingSuccessRate)}
              </div>
              <div className="kp-text-muted">
                Across last {windowRuns ?? "—"} runs
              </div>
            </div>
            <div className="kp-insight">
              <div className="kp-insight-label">Average Resolve Time</div>
              <div className="kp-insight-value">
                {formatMillis(avgResolveTime)}
              </div>
              <div className="kp-text-muted">Based on engine metrics</div>
            </div>
            <div className="kp-insight">
              <div className="kp-insight-label">Fallback Usage</div>
              <div className="kp-insight-value">
                {formatPercent(fallbackUsage)}
              </div>
              <div className="kp-text-muted">
                Steps that used fallback strategies
              </div>
            </div>
          </div>
          {metricsError && (
            <p className="kp-text-error">Metrics: {metricsError}</p>
          )}
        </section>

        {/* Learned selectors */}
        <section className="kp-card" aria-label="Learned selectors">
          <div className="kp-card-header-row">
            <h2 className="kp-card-title">Learned Selectors</h2>
            <button
              type="button"
              className="kp-btn kp-btn-secondary kp-card-action-btn"
              onClick={openGrafana}
            >
              View History
            </button>
          </div>
          <div className="kp-card-body kp-card-table">
            {selectorsError ? (
              <p className="kp-text-error">{selectorsError}</p>
            ) : selectors.length === 0 ? (
              <p className="kp-text-muted">
                No learned selectors recorded yet.
              </p>
            ) : (
              <table className="kp-table" aria-label="Learned selectors">
                <thead>
                  <tr>
                    <th scope="col">Query Text</th>
                    <th scope="col">Primary Locator</th>
                    <th scope="col">Confidence</th>
                    <th scope="col">Times Used</th>
                    <th scope="col">Last Seen At</th>
                  </tr>
                </thead>
                <tbody>
                  {selectors.map((sel) => (
                    <tr key={`${sel.query_text}-${sel.primary_locator}`}>
                      <td>{sel.query_text}</td>
                      <td>{sel.primary_locator}</td>
                      <td>{formatPercent(sel.confidence)}</td>
                      <td>{sel.times_used}</td>
                      <td>{formatDateShort(sel.last_seen_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>

        {/* Flaky tests */}
        <section className="kp-card" aria-label="Flaky tests">
          <h2 className="kp-card-title">Flaky Tests</h2>
          <div className="kp-card-body kp-flaky-grid">
            <div className="kp-flaky-chart">
              <div className="kp-flaky-chart-header">Flakiness over tests</div>
              <div className="kp-flaky-chart-body">
                {flakyChartPoints.length === 0 ? (
                  <div className="kp-text-muted">
                    No flaky patterns detected yet.
                  </div>
                ) : (
                  <ul className="kp-flaky-chart-list">
                    {flakyChartPoints.map((t) => (
                      <li key={t.test_id}>
                        <span className="kp-flaky-dot" />
                        <span className="kp-flaky-name">
                          {t.test_name || t.test_id}
                        </span>
                        <span className="kp-flaky-rate">
                          {formatPercent(t.flakiness_rate)}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
            <div className="kp-flaky-table-wrapper">
              {flakyError ? (
                <p className="kp-text-error">{flakyError}</p>
              ) : flakyTests.length === 0 ? (
                <p className="kp-text-muted">
                  All tests look stable in the current window.
                </p>
              ) : (
                <table className="kp-table" aria-label="Flaky tests table">
                  <thead>
                    <tr>
                      <th scope="col">Test Name</th>
                      <th scope="col">Flake Rate</th>
                      <th scope="col">Recent Failures</th>
                      <th scope="col">Last Failed</th>
                    </tr>
                  </thead>
                  <tbody>
                    {flakyTests.map((t) => (
                      <tr key={t.test_id}>
                        <td>{t.test_name || t.test_id}</td>
                        <td>{formatPercent(t.flakiness_rate)}</td>
                        <td>{t.recent_failures}</td>
                        <td>{formatDateShort(t.last_failed_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </section>
      </div>
    </section>
  );
};
