import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

type RunStats = {
  total?: number;
  passed?: number;
  failed?: number;
};

type RunFields = {
  suite_id?: string;
  suite_name?: string;
  suite_run_id?: string;
  test_id?: string;
  tags?: unknown;
  [key: string]: unknown;
};

type PortalRun = {
  run_id?: string;
  mode?: string;
  started?: number;
  finished?: number;
  duration?: number;
  stats?: RunStats;
  fields?: RunFields;
  status?: string;
};

type RunsResponse = {
  runs?: PortalRun[];
};

type StatusFilter = "all" | "running" | "passed" | "failed";
type DateRangeFilter = "any" | "1h" | "24h" | "7d";
type StatusKind = "running" | "passed" | "failed" | "unknown";

type RunRow = {
  runId: string;
  testName: string;
  statusLabel: string;
  statusKind: StatusKind;
  durationLabel: string;
  startedLabel: string;
  modeLabel: string;
  tags: string[];
  rawStarted?: number;
  rawDuration?: number;
  suiteRunId?: string;
  suiteName?: string;
};

type SuiteItem = {
  kind: "suite";
  suiteRunId: string;
  suiteName: string;
  rows: RunRow[];
};

type RunsItem =
  | { kind: "single"; row: RunRow }
  | SuiteItem;

const formatStatus = (run: PortalRun): { label: string; kind: StatusKind } => {
  const explicit = (run.status || "").toLowerCase();
  if (explicit === "running") {
    return { label: "Running", kind: "running" };
  }
  const stats = run.stats || {};
  const total = Number(stats.total ?? 0);
  const failed = Number(stats.failed ?? 0);
  if (failed > 0) {
    return { label: "Failed", kind: "failed" };
  }
  if (total > 0 && failed === 0) {
    return { label: "Passed", kind: "passed" };
  }
  return { label: "Unknown", kind: "unknown" };
};

const getTestNameFromRun = (run: PortalRun): string => {
  const stats = (run.stats || {}) as any;
  const fields = run.fields || {};
  const fromStats =
    (typeof stats.test_name === "string" && stats.test_name) ||
    (typeof stats.name === "string" && stats.name) ||
    "";
  const fromFields =
    typeof fields.test_name === "string"
      ? (fields.test_name as string)
      : typeof fields.test_id === "string"
      ? (fields.test_id as string)
      : "";
  return fromStats || fromFields || "Unknown";
};

const formatMode = (mode?: string): string => {
  if (!mode) return "Unknown";
  const m = mode.toLowerCase();
  if (m === "live") return "Live";
  if (m === "snapshot") return "Snapshot";
  return "Unknown";
};

const formatDuration = (seconds?: number): string => {
  if (!seconds || !Number.isFinite(seconds) || seconds <= 0) {
    return "—";
  }
  const s = Math.round(seconds);
  if (s < 60) {
    return "< 1 min";
  }
  const minutes = Math.round(s / 60);
  if (minutes < 60) {
    return `${minutes} min`;
  }
  const hours = Math.floor(minutes / 60);
  const remMinutes = minutes % 60;
  if (remMinutes === 0) {
    return `${hours}h`;
  }
  return `${hours}h ${remMinutes}m`;
};

const formatStarted = (started?: number): string => {
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

const formatGroupStatus = (rows: RunRow[]): { label: string; kind: StatusKind } => {
  if (!rows.length) {
    return { label: "Unknown", kind: "unknown" };
  }
  let anyRunning = false;
  let anyFailed = false;
  let anyPassed = false;
  for (const row of rows) {
    if (row.statusKind === "running") {
      anyRunning = true;
    } else if (row.statusKind === "failed") {
      anyFailed = true;
    } else if (row.statusKind === "passed") {
      anyPassed = true;
    }
  }
  if (anyRunning) return { label: "Running", kind: "running" };
  if (anyFailed) return { label: "Failed", kind: "failed" };
  if (anyPassed) return { label: "Passed", kind: "passed" };
  return { label: "Unknown", kind: "unknown" };
};

export const RunsPage = () => {
  const [runs, setRuns] = useState<RunRow[]>([]);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [dateFilter, setDateFilter] = useState<DateRangeFilter>("any");
  const [tagQuery, setTagQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedSuites, setExpandedSuites] = useState<Record<string, boolean>>({});
  const navigate = useNavigate();

  useEffect(() => {
    let cancelled = false;

    const fetchRuns = async () => {
      if (cancelled) return;
      setLoading(true);
      setError(null);
      try {
        const response = await fetch("/api/runs?limit=100");
        if (!response.ok) {
          const text = await response.text();
          throw new Error(`Status ${response.status}: ${text}`);
        }
        const data: RunsResponse = await response.json();
        if (cancelled) return;

        const mapped: RunRow[] = (data.runs || []).map((run) => {
          const status = formatStatus(run);
          const testName = getTestNameFromRun(run);
          const fields = run.fields || {};
          const tagsRaw =
            fields && Array.isArray(fields.tags)
              ? (fields.tags as unknown[])
              : [];
          const tags = tagsRaw
            .map((t) => String(t).trim())
            .filter((t) => t.length > 0);
          const suiteRunId =
            typeof fields.suite_run_id === "string"
              ? (fields.suite_run_id as string)
              : undefined;
          const suiteName =
            (typeof fields.suite_name === "string" && fields.suite_name) ||
            (typeof fields.suite_id === "string" && fields.suite_id) ||
            undefined;

          return {
            runId: String(run.run_id || ""),
            testName,
            statusLabel: status.label,
            statusKind: status.kind,
            durationLabel: formatDuration(run.duration),
            startedLabel: formatStarted(run.started),
            modeLabel: formatMode(run.mode),
            tags,
            rawStarted: run.started,
            rawDuration: run.duration,
            suiteRunId,
            suiteName,
          };
        });

        setRuns(mapped);
      } catch (e) {
        if (!cancelled) {
          setError(
            e instanceof Error ? e.message : "Unable to load runs from portal.",
          );
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

  const filteredRuns = useMemo(() => {
    const nowSec = Date.now() / 1000;
    const q = tagQuery.trim().toLowerCase();

    const matchesDate = (started?: number) => {
      if (!started || !Number.isFinite(started)) return dateFilter === "any";
      const age = nowSec - started;
      if (dateFilter === "any") return true;
      if (dateFilter === "1h") return age <= 60 * 60;
      if (dateFilter === "24h") return age <= 24 * 60 * 60;
      if (dateFilter === "7d") return age <= 7 * 24 * 60 * 60;
      return true;
    };

    return runs.filter((run) => {
      if (statusFilter !== "all" && run.statusKind !== statusFilter) {
        return false;
      }
      if (!matchesDate(run.rawStarted)) {
        return false;
      }
      if (!q) {
        return true;
      }
      const haystack = [
        run.testName,
        run.runId,
        run.tags.join(", "),
        run.modeLabel,
        run.suiteName || "",
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(q);
    });
  }, [runs, statusFilter, dateFilter, tagQuery]);

  const items: RunsItem[] = useMemo(() => {
    const suiteMap = new Map<string, SuiteItem>();
    const out: RunsItem[] = [];
    for (const row of filteredRuns) {
      if (row.suiteRunId) {
        let group = suiteMap.get(row.suiteRunId);
        if (!group) {
          group = {
            kind: "suite",
            suiteRunId: row.suiteRunId,
            suiteName: row.suiteName || row.suiteRunId,
            rows: [],
          };
          suiteMap.set(row.suiteRunId, group);
          out.push(group);
        }
        group.rows.push(row);
      } else {
        out.push({ kind: "single", row });
      }
    }
    return out;
  }, [filteredRuns]);

  const toggleSuite = (id: string) => {
    setExpandedSuites((prev) => ({
      ...prev,
      [id]: !prev[id],
    }));
  };

  return (
    <section className="kp-runs" aria-label="Runs">
      <div className="kp-runs-board">
        <header className="kp-runs-header">
          <h1 className="kp-runs-title">Runs</h1>
        </header>

        <div className="kp-runs-toolbar">
          <div className="kp-runs-filter">
            <label className="kp-field-label" htmlFor="runs-status-filter">
              Status
            </label>
            <select
              id="runs-status-filter"
              className="kp-select"
              value={statusFilter}
              onChange={(event) =>
                setStatusFilter(event.target.value as StatusFilter)
              }
            >
              <option value="all">All</option>
              <option value="running">Running</option>
              <option value="passed">Passed</option>
              <option value="failed">Failed</option>
            </select>
          </div>

          <div className="kp-runs-filter">
            <label className="kp-field-label" htmlFor="runs-date-filter">
              Date range
            </label>
            <select
              id="runs-date-filter"
              className="kp-select"
              value={dateFilter}
              onChange={(event) =>
                setDateFilter(event.target.value as DateRangeFilter)
              }
            >
              <option value="any">Any time</option>
              <option value="1h">Last hour</option>
              <option value="24h">Last 24 hours</option>
              <option value="7d">Last 7 days</option>
            </select>
          </div>

          <div className="kp-runs-search">
            <label className="kp-field-label" htmlFor="runs-tag-filter">
              Tags / search
            </label>
            <div className="kp-tests-search">
              <span className="kp-tests-search-icon" aria-hidden="true">
                🔍
              </span>
              <input
                id="runs-tag-filter"
                type="search"
                className="kp-tests-search-input"
                placeholder="Filter by tag, test, or run id"
                value={tagQuery}
                onChange={(event) => setTagQuery(event.target.value)}
              />
            </div>
          </div>
        </div>

        <div className="kp-runs-table-wrapper">
          {loading ? (
            <div className="kp-tests-loading kp-text-muted">Loading runs...</div>
          ) : error ? (
            <div className="kp-text-error">{error}</div>
          ) : (
            <table className="kp-table kp-runs-table" aria-label="Runs list">
              <thead>
                <tr>
                  <th scope="col">Run ID</th>
                  <th scope="col">Test Name</th>
                  <th scope="col">Status</th>
                  <th scope="col">Duration</th>
                  <th scope="col">Started At</th>
                  <th scope="col">Engine Mode</th>
                  <th scope="col" className="kp-runs-actions-header">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => {
                  if (item.kind === "single") {
                    const row = item.row;
                    return (
                      <tr key={row.runId}>
                        <td>{row.runId}</td>
                        <td>{row.testName}</td>
                        <td>
                          <span
                            className={`kp-status-pill kp-status-pill-${row.statusKind}`}
                          >
                            {row.statusLabel}
                          </span>
                        </td>
                        <td>{row.durationLabel}</td>
                        <td>{row.startedLabel}</td>
                        <td>{row.modeLabel}</td>
                        <td>
                          <div className="kp-runs-actions">
                            <button
                              type="button"
                              className="kp-btn kp-btn-secondary kp-runs-view-btn"
                              onClick={() =>
                                navigate(
                                  `/runs/${encodeURIComponent(row.runId)}`,
                                )
                              }
                            >
                              View
                            </button>
                            <button
                              type="button"
                              className="kp-btn kp-btn-secondary kp-runs-cancel-btn"
                              disabled={row.statusKind !== "running"}
                              title={
                                row.statusKind === "running"
                                  ? "Cancel run (coming soon)"
                                  : "Only running jobs can be canceled"
                              }
                            >
                              Cancel
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  }

                  const group = item;
                  const expanded = !!expandedSuites[group.suiteRunId];
                  const groupStatus = formatGroupStatus(group.rows);
                  const maxDuration = group.rows.reduce<number | undefined>(
                    (acc, row) =>
                      row.rawDuration && Number.isFinite(row.rawDuration)
                        ? acc === undefined
                          ? row.rawDuration
                          : Math.max(acc, row.rawDuration)
                        : acc,
                    undefined,
                  );
                  const groupDurationLabel = formatDuration(maxDuration);
                  const earliestStarted = group.rows.reduce<
                    number | undefined
                  >(
                    (acc, row) =>
                      row.rawStarted && Number.isFinite(row.rawStarted)
                        ? acc === undefined
                          ? row.rawStarted
                          : Math.min(acc, row.rawStarted)
                        : acc,
                    undefined,
                  );
                  const groupStartedLabel = formatStarted(earliestStarted);
                  const modes = Array.from(
                    new Set(group.rows.map((r) => r.modeLabel)),
                  ).filter(Boolean);
                  const groupModeLabel =
                    modes.length === 1 ? modes[0] : "Mixed";

                  const rows: JSX.Element[] = [];
                  rows.push(
                    <tr
                      key={group.suiteRunId}
                      className="kp-table-row-clickable kp-suite-row"
                      onClick={() => toggleSuite(group.suiteRunId)}
                    >
                      <td>{group.suiteRunId}</td>
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
                      <td>
                        <span
                          className={`kp-status-pill kp-status-pill-${groupStatus.kind}`}
                        >
                          {groupStatus.label}
                        </span>
                      </td>
                      <td>{groupDurationLabel}</td>
                      <td>{groupStartedLabel}</td>
                      <td>{groupModeLabel}</td>
                      <td />
                    </tr>,
                  );

                  if (expanded) {
                    for (const row of group.rows) {
                      rows.push(
                        <tr key={row.runId}>
                          <td>{row.runId}</td>
                          <td>{row.testName}</td>
                          <td>
                            <span
                              className={`kp-status-pill kp-status-pill-${row.statusKind}`}
                            >
                              {row.statusLabel}
                            </span>
                          </td>
                          <td>{row.durationLabel}</td>
                          <td>{row.startedLabel}</td>
                          <td>{row.modeLabel}</td>
                          <td>
                            <div className="kp-runs-actions">
                              <button
                                type="button"
                                className="kp-btn kp-btn-secondary kp-runs-view-btn"
                                onClick={() =>
                                  navigate(
                                    `/runs/${encodeURIComponent(row.runId)}`,
                                  )
                                }
                              >
                                View
                              </button>
                              <button
                                type="button"
                                className="kp-btn kp-btn-secondary kp-runs-cancel-btn"
                                disabled={row.statusKind !== "running"}
                                title={
                                  row.statusKind === "running"
                                    ? "Cancel run (coming soon)"
                                    : "Only running jobs can be canceled"
                                }
                              >
                                Cancel
                              </button>
                            </div>
                          </td>
                        </tr>,
                      );
                    }
                  }

                  return rows;
                })}
                {items.length === 0 ? (
                  <tr>
                    <td colSpan={7}>
                      <span className="kp-text-muted">
                        No runs match your filters.
                      </span>
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </section>
  );
};
