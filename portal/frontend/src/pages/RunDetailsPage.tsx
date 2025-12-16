import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useToast } from "../components/ToastContext";

// ---------- Types ----------

type ExecutorBlock = {
  status?: string | null;
  reason?: string | null;
  selector?: unknown;
  signature?: unknown;
};

type HealerBlock = {
  [key: string]: unknown;
};

type PageBrainBlock = {
  candidates?: unknown;
  [key: string]: unknown;
};

type ActionArtifactMap = {
  screenshot_before?: string;
  screenshot_after?: string;
  [key: string]: string | undefined;
};

type ActionRun = {
  ts?: number;
  action_index?: number;
  tool?: string;
  semantic_target?: unknown;
  ok?: boolean;
  reason?: string | null;
  target_signature?: unknown;
  pagebrain?: PageBrainBlock;
  healer?: HealerBlock;
  artifacts?: ActionArtifactMap;
  executor?: ExecutorBlock;
  annotation?: {
    label?: string | null;
    source?: string | null;
    notes?: string | null;
    user_id?: unknown;
  };
};

type RunStats = {
  total?: number;
  passed?: number;
  failed?: number;
  [key: string]: unknown;
};

type RunRecord = {
  run_id: string;
  status?: string;
  mode?: string;
  started?: number;
  stats?: RunStats;
  fields?: Record<string, unknown>;
};

type RunDetailsResponse = {
  run?: RunRecord;
  actions?: ActionRun[];
};

type ArtifactItem = {
  name: string;
  size: number;
  url: string;
};

type ArtifactsResponse = {
  run_id: string;
  items: ArtifactItem[];
};

type RunsListResponse = {
  runs?: RunRecord[];
};

type StepStatus = "passed" | "failed" | "healed" | "retried" | "unknown";

type TimelineStep = {
  index: number;
  label: string;
  durationLabel: string;
  status: StepStatus;
  reason?: string | null;
   annotationLabel?: string | null;
  action: ActionRun;
};

type ArtifactTabId =
  | "screenshotAfter"
  | "screenshotBefore"
  | "domSnapshot"
  | "console"
  | "network"
  | "resolve"
  | "metrics";

// ---------- Helpers ----------

const formatDurationSeconds = (start?: number, end?: number): string => {
  if (!start || !end || !Number.isFinite(start) || !Number.isFinite(end)) {
    return "—";
  }
  const sec = Math.max(0, end - start);
  if (sec < 1) return "< 1s";
  if (sec < 60) return `${sec.toFixed(1)}s`;
  const minutes = Math.round(sec / 60);
  return `${minutes}m`;
};

const formatStepStatus = (action: ActionRun): StepStatus => {
  const ok = !!action.ok;
  const healer = action.healer || {};
  const hadHeal =
    healer && typeof healer === "object" && Object.keys(healer).length > 0;

  if (ok && hadHeal) return "healed";
  if (ok) return "passed";
  if (!ok && hadHeal) return "retried";
  if (!ok) return "failed";
  return "unknown";
};

const formatRunStarted = (started?: number): string => {
  if (!started || Number.isNaN(started)) return "—";
  try {
    const date = new Date(started * 1000);
    if (Number.isNaN(date.getTime())) return "—";
    return date.toLocaleString();
  } catch {
    return "—";
  }
};

const formatMode = (mode?: string): string => {
  if (!mode) return "Unknown";
  const m = mode.toLowerCase();
  if (m === "live") return "Live";
  if (m === "snapshot") return "Snapshot";
  return "Unknown";
};

const formatStepLabel = (action: ActionRun): string => {
  const target = action.semantic_target;
  if (typeof target === "string") return target;
  if (target && typeof target === "object") {
    const anyTarget = target as any;
    if (typeof anyTarget.text === "string" && anyTarget.text.trim()) {
      return anyTarget.text;
    }
  }
  if (typeof action.tool === "string") {
    return action.tool;
  }
  return "Step";
};

const guessArtifactTabs = (
  artifacts: ArtifactItem[],
): Record<ArtifactTabId, ArtifactItem | null> => {
  const byName = new Map<string, ArtifactItem>();
  for (const it of artifacts) {
    byName.set(it.name, it);
  }

  const findName = (pred: (name: string) => boolean): ArtifactItem | null => {
    for (const it of artifacts) {
      if (pred(it.name)) return it;
    }
    return null;
  };

  return {
    screenshotAfter:
      byName.get("screenshot") ||
      findName((n) => n.toLowerCase().includes("after")) ||
      null,
    screenshotBefore:
      findName((n) => n.toLowerCase().includes("before")) || null,
    domSnapshot:
      byName.get("input") ||
      findName((n) => n.toLowerCase().includes("dom")) ||
      null,
    console:
      findName(
        (n) =>
          n.toLowerCase().includes("console") ||
          n.toLowerCase().includes("log"),
      ) || null,
    network:
      findName(
        (n) =>
          n.toLowerCase().includes("network") ||
          n.toLowerCase().includes("har"),
      ) || null,
    resolve:
      byName.get("resolve") ||
      findName((n) => n.toLowerCase().includes("resolve")) ||
      null,
    metrics:
      findName((n) => n.toLowerCase().includes("metrics")) ||
      null,
  };
};

const isImageArtifact = (item: ArtifactItem | null): boolean => {
  if (!item) return false;
  const name = item.name.toLowerCase();
  if (name.endsWith(".png") || name.endsWith(".jpg") || name.endsWith(".jpeg")) {
    return true;
  }
  // Treat anything starting with "screenshot" as image (FSArtifactStore names).
  return name.startsWith("screenshot");
};

// ---------- Component ----------

export const RunDetailsPage = () => {
  const { runId } = useParams<{ runId: string }>();
  const [run, setRun] = useState<RunRecord | null>(null);
  const [steps, setSteps] = useState<TimelineStep[]>([]);
  const [artifacts, setArtifacts] = useState<ArtifactItem[]>([]);
  const [activeStepIndex, setActiveStepIndex] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<ArtifactTabId>("screenshotAfter");
  const [artifactContent, setArtifactContent] = useState<string | null>(null);
  const [artifactLoading, setArtifactLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [suiteChildren, setSuiteChildren] = useState<RunRecord[]>([]);
  const toast = useToast();
  const navigate = useNavigate();

  const runIdSafe = runId || "";

  useEffect(() => {
    let cancelled = false;

    const fetchDetails = async () => {
      if (!runIdSafe) return;
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(
          `/api/runs/${encodeURIComponent(runIdSafe)}/details`,
        );
        if (!res.ok) {
          const text = await res.text();
          throw new Error(`Status ${res.status}: ${text}`);
        }
        const data: RunDetailsResponse = await res.json();
        if (cancelled) return;
        const runRec: RunRecord | null = data.run || null;
        const actions: ActionRun[] = data.actions || [];
        setRun(runRec);

        const baseStarted = runRec?.started ?? actions[0]?.ts;
        const stepsMapped: TimelineStep[] = actions.map((action, idx) => {
          const status = formatStepStatus(action);
          const durationLabel = formatDurationSeconds(baseStarted, action.ts);
          const ann: any = (action as any).annotation || null;
          return {
            index: idx,
            label: formatStepLabel(action),
            durationLabel,
            status,
            reason: action.reason,
            annotationLabel:
              ann && typeof ann.label === "string" ? ann.label : null,
            action,
          };
        });
        setSteps(stepsMapped);
        if (stepsMapped.length) {
          setActiveStepIndex(0);
        }

        // If this looks like a suite_run_id (no actions & unknown status),
        // fetch child runs that reference it via fields.suite_run_id.
        if (!actions.length && runRec && runRec.status === "unknown") {
          const listRes = await fetch("/api/runs?limit=200");
          if (listRes.ok) {
            const listData: RunsListResponse = await listRes.json();
            const children = (listData.runs || []).filter((r) => {
              const fields = r.fields || {};
              return (
                typeof fields["suite_run_id"] === "string" &&
                (fields["suite_run_id"] as string) === runIdSafe
              );
            });
            if (!cancelled) {
              setSuiteChildren(children);
            }
          }
        } else {
          setSuiteChildren([]);
        }
      } catch (e) {
        if (!cancelled) {
          setError(
            e instanceof Error
              ? e.message
              : "Failed to load run details from portal.",
          );
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    const fetchArtifacts = async () => {
      if (!runIdSafe) return;
      try {
        const res = await fetch(
          `/api/runs/${encodeURIComponent(runIdSafe)}/artifacts`,
        );
        if (!res.ok) return;
        const data: ArtifactsResponse = await res.json();
        setArtifacts(data.items || []);
      } catch {
        // optional
      }
    };

    fetchDetails();
    fetchArtifacts();
    return () => {
      cancelled = true;
    };
  }, [runIdSafe]);

  const artifactTabs = useMemo(
    () => guessArtifactTabs(artifacts),
    [artifacts],
  );

  const selectedStep =
    activeStepIndex != null ? steps[activeStepIndex] : null;

  const currentArtifact = useMemo(() => {
    const global = artifactTabs[activeTab] || null;

    // For screenshots, prefer per-step artifacts when available.
    if (
      selectedStep &&
      (activeTab === "screenshotAfter" || activeTab === "screenshotBefore")
    ) {
      const stepArtifacts = selectedStep.action.artifacts || {};
      let name: string | undefined;
      if (activeTab === "screenshotAfter") {
        name = stepArtifacts.screenshot_after;
      } else if (activeTab === "screenshotBefore") {
        name = stepArtifacts.screenshot_before;
      }
      if (name) {
        const match =
          artifacts.find((item) => item.name === name) || null;
        if (match) {
          return match;
        }
      }
    }

    return global;
  }, [artifactTabs, activeTab, selectedStep, artifacts]);

  useEffect(() => {
    const current = currentArtifact;
    if (!current) {
      setArtifactContent(null);
      return;
    }
    if (isImageArtifact(current)) {
      // Image is shown via <img>; no need to fetch text content.
      setArtifactContent(null);
      return;
    }
    const isTextLike =
      current.name.endsWith(".json") ||
      current.name.endsWith(".jsonl") ||
      current.name.endsWith(".log") ||
      current.name.endsWith(".txt") ||
      current.name === "resolve" ||
      current.name === "steps" ||
      current.name === "log" ||
      current.name === "input";
    if (!isTextLike) {
      setArtifactContent(null);
      return;
    }
    let cancelled = false;
    const load = async () => {
      setArtifactLoading(true);
      try {
        const res = await fetch(current.url);
        const text = await res.text();
        if (!cancelled) {
          setArtifactContent(text);
        }
      } catch {
        if (!cancelled) {
          setArtifactContent("Unable to load artifact content.");
        }
      } finally {
        if (!cancelled) {
          setArtifactLoading(false);
        }
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [currentArtifact]);

  const handleRerunTest = async () => {
    const testId =
      (run?.fields && (run.fields["test_id"] as string | undefined)) || null;
    if (!testId) {
      toast.showToast("error", "Cannot rerun: missing test id on this run.");
      return;
    }
    try {
      const body: Record<string, unknown> = { mode: "live" };
      const url = `/api/tests/${encodeURIComponent(testId)}/runs`;
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`Status ${res.status}: ${text}`);
      }
      const data = (await res.json()) as { run_id?: string };
      const newRunId = data.run_id;
      toast.showToast(
        "success",
        newRunId
          ? `Rerun started (run ID: ${newRunId}).`
          : "Rerun started.",
      );
      if (newRunId) {
        navigate(`/runs/${encodeURIComponent(newRunId)}`);
      }
    } catch (e) {
      toast.showToast(
        "error",
        e instanceof Error ? e.message : "Failed to rerun test.",
      );
    }
  };

  const handleRerunStep = () => {
    toast.showToast(
      "info",
      "Rerunning individual steps is not implemented yet.",
    );
  };

  const handleExportArtifacts = () => {
    if (!runIdSafe) return;
    try {
      window.open(
        `/api/runs/${encodeURIComponent(runIdSafe)}/artifacts`,
        "_blank",
      );
    } catch {
      toast.showToast(
        "info",
        "Artifacts can be downloaded from the Artifacts page for now.",
      );
    }
  };

  const handleCopyStepLink = (index: number) => {
    const url = new URL(window.location.href);
    url.hash = `step-${index}`;
    try {
      navigator.clipboard.writeText(url.toString());
      toast.showToast("success", "Step link copied to clipboard.");
    } catch {
      toast.showToast("error", "Unable to copy link to clipboard.");
    }
  };

  const handleSetStepAnnotation = async (
    stepIndex: number,
    label: "passed" | "failed",
  ) => {
    if (!runIdSafe) return;
    const step = steps[stepIndex];
    if (!step) return;
    const action = step.action;
    const actionIndex =
      typeof action.action_index === "number"
        ? action.action_index
        : step.index;

    const payload: Record<string, unknown> = {
      action_index: actionIndex,
      label,
      source: "human_truth",
    };

    if (action.executor && typeof action.executor.selector === "object") {
      payload.selector = action.executor.selector as Record<string, unknown>;
    }
    if (action.tool && typeof action.tool === "string") {
      payload.tool = action.tool;
    }
    if (
      action.target_signature &&
      typeof action.target_signature === "object"
    ) {
      payload.target_signature =
        action.target_signature as Record<string, unknown>;
    }

    try {
      const res = await fetch(
        `/api/runs/${encodeURIComponent(runIdSafe)}/annotations`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
      );
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`Status ${res.status}: ${text}`);
      }
      const ann = (await res.json()) as {
        label?: string;
        source?: string;
        notes?: string | null;
      };
      const annLabel = ann.label || label;
      setSteps((prev) =>
        prev.map((st) =>
          st.index === step.index
            ? {
                ...st,
                annotationLabel: annLabel,
                action: { ...st.action, annotation: ann },
              }
            : st,
        ),
      );
      toast.showToast(
        "success",
        label === "passed"
          ? "Marked step as passed."
          : "Marked step as failed.",
      );
    } catch (e) {
      toast.showToast(
        "error",
        e instanceof Error
          ? e.message
          : "Failed to save step annotation.",
      );
    }
  };

  const isSuiteRunView = !steps.length && suiteChildren.length > 0;

  return (
    <section className="kp-run-details" aria-label="Run details">
      <div className="kp-run-details-grid">
        {/* Left: Step timeline or suite children */}
        <aside className="kp-run-timeline">
          <header className="kp-panel-header">
            <h2 className="kp-panel-title">
              {isSuiteRunView ? "Suite Runs" : "Step Timeline"}
            </h2>
          </header>
          <div className="kp-panel-body kp-run-timeline-body">
            {loading ? (
              <div className="kp-tests-loading kp-text-muted">
                Loading run details...
              </div>
            ) : error ? (
              <div className="kp-text-error">{error}</div>
            ) : isSuiteRunView ? (
              <div>
                <p className="kp-text-muted">
                  This identifier represents a suite run. Select one of the
                  child test runs below to inspect its step timeline.
                </p>
                <ul className="kp-run-steps-list">
                  {suiteChildren.map((child) => {
                    const fields = child.fields || {};
                    const testId =
                      (fields["test_name"] as string) ||
                      (fields["test_id"] as string) ||
                      "Unknown";
                    const stats = child.stats || {};
                    const total = Number(stats.total ?? 0);
                    const failed = Number(stats.failed ?? 0);
                    const statusLabel =
                      failed > 0
                        ? "Failed"
                        : total > 0
                        ? "Passed"
                        : "Unknown";
                    const statusKind =
                      failed > 0
                        ? "failed"
                        : total > 0
                        ? "passed"
                        : "unknown";
                    return (
                      <li
                        key={child.run_id}
                        className="kp-run-step"
                        onClick={() =>
                          navigate(`/runs/${encodeURIComponent(child.run_id)}`)
                        }
                      >
                        <div className="kp-run-step-main">
                          <div className="kp-run-step-index">•</div>
                          <div className="kp-run-step-text">
                            <div className="kp-run-step-title">{testId}</div>
                            <div className="kp-run-step-meta">
                              <span className={`kp-run-step-status`}>
                                {statusLabel}
                              </span>
                              <span className="kp-run-step-duration">
                                {formatRunStarted(child.started)}
                              </span>
                            </div>
                          </div>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ) : steps.length === 0 ? (
              <div className="kp-text-muted">
                No step timeline is available for this run.
              </div>
            ) : (
              <ol className="kp-run-steps-list">
                {steps.map((step, idx) => {
                  const isActive = idx === activeStepIndex;
                  const annLower = (step.annotationLabel || "")
                    .toLowerCase()
                    .trim();
                  const passedActive = annLower.startsWith("pass");
                  const failedActive = annLower.startsWith("fail");
                  const classes = [
                    "kp-run-step",
                    `kp-run-step-${step.status}`,
                    isActive ? "kp-run-step-active" : "",
                  ]
                    .filter(Boolean)
                    .join(" ");
                  const hasError =
                    step.status === "failed" || !!step.reason;
                  return (
                    <li
                      key={step.index}
                      id={`step-${step.index}`}
                      className={classes}
                      onClick={() => setActiveStepIndex(idx)}
                    >
                      <div className="kp-run-step-main">
                        <div className="kp-run-step-index">
                          {step.index + 1}
                        </div>
                        <div className="kp-run-step-text">
                          <div className="kp-run-step-title">{step.label}</div>
                          <div className="kp-run-step-meta">
                            <span className="kp-run-step-status">
                              {step.status === "passed" && "Passed"}
                              {step.status === "failed" && "Failed"}
                              {step.status === "healed" && "Healed"}
                              {step.status === "retried" && "Retried"}
                              {step.status === "unknown" && "Unknown"}
                            </span>
                            <span className="kp-run-step-duration">
                              {step.durationLabel}
                            </span>
                            {step.annotationLabel && (
                              <span
                                className={`kp-run-step-annotation ${
                                  step.annotationLabel
                                    .toLowerCase()
                                    .startsWith("fail")
                                    ? "kp-run-step-annotation-failed"
                                    : "kp-run-step-annotation-passed"
                                }`}
                              >
                                Human: {step.annotationLabel}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                      {hasError && (
                        <div className="kp-run-step-error-banner">
                          <div className="kp-run-step-error-title">
                            Error: {step.reason || "Step failed"}
                          </div>
                          <div className="kp-run-step-error-sub">
                            Click the step to inspect resolver candidates and
                            healer attempts on the right.
                          </div>
                        </div>
                      )}
                      <div className="kp-run-step-toggles">
                        <button
                          type="button"
                          className={`kp-step-annotate-btn ${
                            passedActive
                              ? "kp-step-annotate-btn-passed-on"
                              : "kp-step-annotate-btn-passed-off"
                          }`}
                          onClick={(event) => {
                            event.stopPropagation();
                            handleSetStepAnnotation(idx, "passed");
                          }}
                        >
                          Passed
                        </button>
                        <button
                          type="button"
                          className={`kp-step-annotate-btn ${
                            failedActive
                              ? "kp-step-annotate-btn-failed-on"
                              : "kp-step-annotate-btn-failed-off"
                          }`}
                          onClick={(event) => {
                            event.stopPropagation();
                            handleSetStepAnnotation(idx, "failed");
                          }}
                        >
                          Failed
                        </button>
                        <button
                          type="button"
                          className="kp-link-button"
                          onClick={(event) => {
                            event.stopPropagation();
                            setActiveStepIndex(idx);
                          }}
                      >
                          Show Resolver Candidates
                        </button>
                        <button
                          type="button"
                          className="kp-link-button"
                          onClick={(event) => {
                            event.stopPropagation();
                            setActiveStepIndex(idx);
                          }}
                        >
                          Show Heal Attempts
                        </button>
                        <button
                          type="button"
                          className="kp-link-button"
                          onClick={(event) => {
                            event.stopPropagation();
                            handleCopyStepLink(step.index);
                          }}
                        >
                          Copy Link
                        </button>
                      </div>
                    </li>
                  );
                })}
              </ol>
            )}
          </div>
        </aside>

        {/* Right: Artifact viewer */}
        <section className="kp-run-artifacts">
          <header className="kp-panel-header">
            <h2 className="kp-panel-title">Artifact Viewer</h2>
          </header>
          <div className="kp-panel-body kp-run-artifacts-body">
            <div className="kp-run-summary">
              <div>
                <div className="kp-run-summary-title">
                  Run {run?.run_id || runIdSafe}
                </div>
                <div className="kp-run-summary-sub">
                  Mode: {formatMode(run?.mode)} · Started:{" "}
                  {formatRunStarted(run?.started)}
                </div>
              </div>
            </div>

            <div className="kp-run-artifact-tabs">
              <button
                type="button"
                className={
                  activeTab === "screenshotAfter"
                    ? "kp-run-tab kp-run-tab-active"
                    : "kp-run-tab"
                }
                onClick={() => setActiveTab("screenshotAfter")}
              >
                Screenshot (After)
              </button>
              <button
                type="button"
                className={
                  activeTab === "screenshotBefore"
                    ? "kp-run-tab kp-run-tab-active"
                    : "kp-run-tab"
                }
                onClick={() => setActiveTab("screenshotBefore")}
              >
                Screenshot (Before)
              </button>
              <button
                type="button"
                className={
                  activeTab === "domSnapshot"
                    ? "kp-run-tab kp-run-tab-active"
                    : "kp-run-tab"
                }
                onClick={() => setActiveTab("domSnapshot")}
              >
                DOM Snapshot
              </button>
              <button
                type="button"
                className={
                  activeTab === "console"
                    ? "kp-run-tab kp-run-tab-active"
                    : "kp-run-tab"
                }
                onClick={() => setActiveTab("console")}
              >
                Console Logs
              </button>
              <button
                type="button"
                className={
                  activeTab === "network"
                    ? "kp-run-tab kp-run-tab-active"
                    : "kp-run-tab"
                }
                onClick={() => setActiveTab("network")}
              >
                Network Logs
              </button>
              <button
                type="button"
                className={
                  activeTab === "resolve"
                    ? "kp-run-tab kp-run-tab-active"
                    : "kp-run-tab"
                }
                onClick={() => setActiveTab("resolve")}
              >
                Resolve JSON
              </button>
              <button
                type="button"
                className={
                  activeTab === "metrics"
                    ? "kp-run-tab kp-run-tab-active"
                    : "kp-run-tab"
                }
                onClick={() => setActiveTab("metrics")}
              >
                Metrics
              </button>
            </div>

            <div className="kp-run-artifact-content">
              {artifactLoading ? (
                <div className="kp-tests-loading kp-text-muted">
                  Loading artifact...
                </div>
              ) : (
                <>
                  {(() => {
                    const current = currentArtifact;
                    if (!current) {
                      return (
                        <div className="kp-text-muted">
                          No artifact available for this tab.
                        </div>
                      );
                    }
                    if (isImageArtifact(current)) {
                      return (
                        <div className="kp-run-screenshot-frame">
                          <img
                            src={current.url}
                            alt={current.name}
                            className="kp-run-screenshot-img"
                          />
                        </div>
                      );
                    }
                    return (
                      <pre className="kp-plan-json">
                        {artifactContent || "Select an artifact to view."}
                      </pre>
                    );
                  })()}
                </>
              )}
            </div>

            {selectedStep && (
              <div className="kp-run-annotation-actions">
                {(() => {
                  const annLower = (selectedStep.annotationLabel || "")
                    .toLowerCase()
                    .trim();
                  const passedActive = annLower.startsWith("pass");
                  const failedActive = annLower.startsWith("fail");
                  return (
                    <>
                      <button
                        type="button"
                        className={`kp-step-annotate-btn ${
                          passedActive
                            ? "kp-step-annotate-btn-passed-on"
                            : "kp-step-annotate-btn-passed-off"
                        }`}
                        onClick={() =>
                          handleSetStepAnnotation(
                            activeStepIndex ?? selectedStep.index,
                            "passed",
                          )
                        }
                      >
                        Passed
                      </button>
                      <button
                        type="button"
                        className={`kp-step-annotate-btn ${
                          failedActive
                            ? "kp-step-annotate-btn-failed-on"
                            : "kp-step-annotate-btn-failed-off"
                        }`}
                        onClick={() =>
                          handleSetStepAnnotation(
                            activeStepIndex ?? selectedStep.index,
                            "failed",
                          )
                        }
                      >
                        Failed
                      </button>
                    </>
                  );
                })()}
              </div>
            )}

            <footer className="kp-run-actions-footer">
              <button
                type="button"
                className="kp-btn kp-btn-secondary"
                onClick={handleRerunTest}
              >
                Rerun Test
              </button>
              <button
                type="button"
                className="kp-btn kp-btn-secondary"
                onClick={handleRerunStep}
                disabled={activeStepIndex == null}
              >
                Rerun Step
              </button>
              <button
                type="button"
                className="kp-btn kp-btn-secondary"
                onClick={handleExportArtifacts}
              >
                Export Artifacts
              </button>
              <button
                type="button"
                className="kp-btn kp-btn-ghost"
                onClick={() => navigate("/runs")}
              >
                Back to Runs
              </button>
            </footer>
          </div>
        </section>
      </div>
    </section>
  );
};
