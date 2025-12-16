import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

type RunStats = {
  total?: number;
  passed?: number;
  failed?: number;
  heal_attempts?: number;
  heal_successes?: number;
  healed_rate?: number;
};

type RunFields = {
  suite_id?: string;
  suite_name?: string;
  suite_run_id?: string;
  test_id?: string;
  [key: string]: unknown;
};

type RecentRun = {
  run_id: string;
  mode?: string;
  started?: number;
  stats?: RunStats;
  fields?: RunFields;
};

type RunsResponse = {
  runs?: RecentRun[];
};

type DashboardSummary = {
  healingSuccessRate: number | null;
  successRate: number | null;
  avgResolveTimeSeconds: number | null;
  flakyTestsCount: number | null;
};

const computeSummary = (runs: RecentRun[]): DashboardSummary => {
  if (!runs.length) {
    return {
      healingSuccessRate: null,
      successRate: null,
      avgResolveTimeSeconds: null,
      flakyTestsCount: null,
    };
  }
  let totalAttempts = 0;
  let totalSuccesses = 0;
  let passedRuns = 0;

  for (const run of runs) {
    const stats = run.stats || {};
    const attempts = Number(stats.heal_attempts ?? 0);
    const successes = Number(stats.heal_successes ?? 0);
    totalAttempts += attempts;
    totalSuccesses += successes;
    const total = Number(stats.total ?? 0);
    const failed = Number(stats.failed ?? 0);
    if (total > 0 && failed === 0) {
      passedRuns += 1;
    }
  }

  const healingSuccessRate =
    totalAttempts > 0 ? (totalSuccesses / totalAttempts) * 100 : null;
  const successRate = runs.length > 0 ? (passedRuns / runs.length) * 100 : null;

  return {
    healingSuccessRate,
    successRate,
    // Detailed resolve timing and flaky test counts will be wired
    // from ADR-0004 metrics in a later iteration.
    avgResolveTimeSeconds: null,
    flakyTestsCount: null,
  };
};

const getTestName = (run: RecentRun): string => {
  const stats = (run.stats || {}) as any;
  const fields = run.fields || {};
  const fromStats = (stats.test_name as string) || (stats.name as string);
  const fromFields =
    typeof fields.test_id === "string" ? (fields.test_id as string) : undefined;
  return fromStats || fromFields || "Unknown";
};

const formatStatus = (run: RecentRun): { label: string; kind: string } => {
  const stats = run.stats || {};
  const total = Number(stats.total ?? 0);
  const failed = Number(stats.failed ?? 0);
  if (total === 0 && failed === 0) {
    return { label: "Unknown", kind: "unknown" };
  }
  if (failed > 0) {
    return { label: "Failed", kind: "failed" };
  }
  if (total > 0 && failed === 0) {
    return { label: "Passed", kind: "passed" };
  }
  return { label: "Unknown", kind: "unknown" };
};

const formatStarted = (started?: number) => {
  if (!started || Number.isNaN(started)) {
    return "—";
  }
  try {
    const date = new Date(started * 1000);
    if (Number.isNaN(date.getTime())) {
      return "—";
    }
    return date.toLocaleString();
  } catch {
    return "—";
  }
};

export const DashboardPage = () => {
  const [runs, setRuns] = useState<RecentRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    let cancelled = false;

    const fetchRuns = async () => {
      try {
        if (cancelled) {
          return;
        }
        setLoading(true);
        const response = await fetch("/api/runs?limit=10");
        if (!response.ok) {
          throw new Error(`Status ${response.status}`);
        }
        const data: RunsResponse = await response.json();
        if (!cancelled) {
          setRuns(data.runs || []);
          setError(null);
        }
      } catch {
        if (!cancelled) {
          setError("Unable to load recent runs.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    fetchRuns();
    const id = window.setInterval(fetchRuns, 10000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  const summary = computeSummary(runs);

  type DashboardItem =
    | { kind: "single"; run: RecentRun }
    | {
        kind: "suite";
        suiteRunId: string;
        suiteName: string;
        started?: number;
        runs: RecentRun[];
      };

  const items: DashboardItem[] = [];
  const suiteMap = new Map<string, DashboardItem & { kind: "suite" }>();

  for (const run of runs) {
    const fields = run.fields || {};
    const suiteRunId =
      typeof fields.suite_run_id === "string" ? fields.suite_run_id : undefined;
    if (suiteRunId) {
      let group = suiteMap.get(suiteRunId);
      if (!group) {
        const suiteName =
          (typeof fields.suite_name === "string" && fields.suite_name) ||
          (typeof fields.suite_id === "string" && fields.suite_id) ||
          "Suite";
        group = {
          kind: "suite",
          suiteRunId,
          suiteName,
          started: run.started,
          runs: [],
        };
        suiteMap.set(suiteRunId, group);
        items.push(group);
      }
      group.runs.push(run);
    } else {
      items.push({ kind: "single", run });
    }
  }

  const [expandedSuites, setExpandedSuites] = useState<Record<string, boolean>>(
    {},
  );

  const toggleSuite = (id: string) => {
    setExpandedSuites((prev) => ({
      ...prev,
      [id]: !prev[id],
    }));
  };

  const formatGroupStatus = (group: {
    runs: RecentRun[];
  }): { label: string; kind: string } => {
    if (!group.runs.length) {
      return { label: "Unknown", kind: "unknown" };
    }
    let anyFailed = false;
    let anyPassed = false;
    for (const run of group.runs) {
      const stats = run.stats || {};
      const total = Number(stats.total ?? 0);
      const failed = Number(stats.failed ?? 0);
      if (failed > 0) {
        anyFailed = true;
      } else if (total > 0) {
        anyPassed = true;
      }
    }
    if (anyFailed) {
      return { label: "Failed", kind: "failed" };
    }
    if (anyPassed) {
      return { label: "Passed", kind: "passed" };
    }
    return { label: "Unknown", kind: "unknown" };
  };

  return (
    <section className="kp-dashboard" aria-label="Dashboard">
      <div className="kp-dashboard-header-card">
        <div>
          <h1 className="kp-dashboard-title">Dashboard</h1>
          <p className="kp-dashboard-subtitle">
            Central place for tests, runs, and healing insights.
          </p>
        </div>
        <div className="kp-dashboard-badge" aria-label="Current profile">
          Local Workspace
        </div>
      </div>

      <div className="kp-dashboard-grid">
        <section className="kp-card" aria-label="Quick actions">
          <h2 className="kp-card-title">Quick Actions</h2>
          <div className="kp-card-body kp-card-actions">
            <button
              type="button"
              className="kp-btn kp-btn-primary kp-card-action-btn"
              onClick={() => navigate("/tests")}
            >
              Create New Test
            </button>
            <button
              type="button"
              className="kp-btn kp-btn-secondary kp-card-action-btn"
              onClick={() => navigate("/suites/new")}
            >
              Run a Test Suite
            </button>
            <button
              type="button"
              className="kp-btn kp-btn-secondary kp-card-action-btn"
              onClick={() => navigate("/snapshots/upload")}
            >
              Upload HTML Snapshot
            </button>
          </div>
        </section>

        <section className="kp-card" aria-label="Recent runs">
          <div className="kp-card-header-row">
            <h2 className="kp-card-title">Recent Runs</h2>
          </div>
          <div className="kp-card-body kp-card-table">
            {loading ? (
              <p className="kp-text-muted">Loading recent runs…</p>
            ) : error ? (
              <p className="kp-text-error">{error}</p>
            ) : runs.length === 0 ? (
              <p className="kp-text-muted">No runs yet. Start one above.</p>
            ) : (
              <table className="kp-table" aria-label="Recent runs table">
                <thead>
                  <tr>
                    <th scope="col">Test Name</th>
                    <th scope="col">Run ID</th>
                    <th scope="col">Status</th>
                    <th scope="col">Started At</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => {
                    if (item.kind === "single") {
                      const run = item.run;
                      const status = formatStatus(run);
                      const testName = getTestName(run);
                      return (
                        <tr
                          key={run.run_id}
                          className="kp-table-row-clickable"
                          onClick={() => navigate(`/runs/${run.run_id}`)}
                        >
                          <td>{testName}</td>
                          <td>{run.run_id}</td>
                          <td>
                            <span
                              className={`kp-status-pill kp-status-pill-${status.kind}`}
                            >
                              {status.label}
                            </span>
                          </td>
                          <td>{formatStarted(run.started)}</td>
                        </tr>
                      );
                    }
                    const group = item;
                    const expanded = !!expandedSuites[group.suiteRunId];
                    const groupStatus = formatGroupStatus(group);
                    const started =
                      group.started ?? group.runs[0]?.started ?? undefined;
                    return (
                      <>
                        <tr
                          key={group.suiteRunId}
                          className="kp-table-row-clickable kp-suite-row"
                          onClick={() => toggleSuite(group.suiteRunId)}
                        >
                          <td className="kp-suite-cell">
                            <button
                              type="button"
                              className="kp-suite-toggle"
                              onClick={(event) => {
                                event.stopPropagation();
                                toggleSuite(group.suiteRunId);
                              }}
                              aria-label={
                                expanded
                                  ? `Collapse suite ${group.suiteName}`
                                  : `Expand suite ${group.suiteName}`
                              }
                            >
                              {expanded ? "▾" : "▸"}
                            </button>
                            <span className="kp-suite-label">Suite</span>
                            <span className="kp-suite-name">
                              {group.suiteName}
                            </span>
                          </td>
                          <td>{group.suiteRunId}</td>
                          <td>
                            <span
                              className={`kp-status-pill kp-status-pill-${groupStatus.kind}`}
                            >
                              {groupStatus.label}
                            </span>
                          </td>
                          <td>{formatStarted(started)}</td>
                        </tr>
                        {expanded &&
                          group.runs.map((run) => {
                            const status = formatStatus(run);
                            const testName = getTestName(run);
                            return (
                              <tr
                                key={run.run_id}
                                className="kp-table-row-clickable kp-suite-child-row"
                                onClick={() => navigate(`/runs/${run.run_id}`)}
                              >
                                <td className="kp-suite-child-cell">
                                  <span
                                    className="kp-suite-child-bullet"
                                    aria-hidden="true"
                                  >
                                    ↳
                                  </span>
                                  <span>{testName}</span>
                                </td>
                                <td>{run.run_id}</td>
                                <td>
                                  <span
                                    className={`kp-status-pill kp-status-pill-${status.kind}`}
                                  >
                                    {status.label}
                                  </span>
                                </td>
                                <td>{formatStarted(run.started)}</td>
                              </tr>
                            );
                          })}
                      </>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        </section>

        <section className="kp-card" aria-label="Insights summary">
          <h2 className="kp-card-title">Insights Summary</h2>
          <div className="kp-card-body kp-insights-grid">
            <div className="kp-insight">
              <div className="kp-insight-label">Healing Success Rate</div>
              <div className="kp-insight-value">
                {summary.healingSuccessRate != null
                  ? `${summary.healingSuccessRate.toFixed(0)}%`
                  : "—"}
              </div>
            </div>
            <div className="kp-insight">
              <div className="kp-insight-label">Test Success Rate</div>
              <div className="kp-insight-value">
                {summary.successRate != null
                  ? `${summary.successRate.toFixed(0)}%`
                  : "—"}
              </div>
            </div>
            <div className="kp-insight">
              <div className="kp-insight-label">Avg Resolve Time</div>
              <div className="kp-insight-value">
                {summary.avgResolveTimeSeconds != null
                  ? `${summary.avgResolveTimeSeconds.toFixed(1)}s`
                  : "—"}
              </div>
            </div>
            <div className="kp-insight">
              <div className="kp-insight-label">Flaky Tests Count</div>
              <div className="kp-insight-value">
                {summary.flakyTestsCount != null
                  ? summary.flakyTestsCount
                  : "—"}
              </div>
            </div>
          </div>
        </section>
      </div>

      <div className="kp-dashboard-footer">
        <button
          type="button"
          className="kp-btn kp-btn-ghost"
          onClick={() => navigate("/settings")}
        >
          Settings
        </button>
      </div>
    </section>
  );
};
