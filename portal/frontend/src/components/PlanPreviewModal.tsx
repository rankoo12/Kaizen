import type { KeyboardEvent } from "react";

type PlanPreview = {
  plan: unknown;
  valid: boolean;
  errors: string[];
  model?: string | null;
};

type Props = {
  open: boolean;
  plan: PlanPreview | null;
  planName: string;
  stepTexts: string[];
  onClose: () => void;
  onRun: () => void;
  onUpdatePreview: () => void;
  onReportIssue?: () => void;
};

export const PlanPreviewModal = ({
  open,
  plan,
  planName,
  stepTexts,
  onClose,
  onRun,
  onUpdatePreview,
  onReportIssue,
}: Props) => {
  if (!open) return null;

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.stopPropagation();
      onClose();
    }
  };

  const summaryText =
    stepTexts.length === 0
      ? "No steps available."
      : stepTexts.join("\n");

  return (
    <div
      className="kp-modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-label="Plan viewer"
      onClick={onClose}
      onKeyDown={handleKeyDown}
    >
      <div
        className="kp-modal"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="kp-plan-viewer">
          <section className="kp-plan-viewer-board">
            <header className="kp-plan-viewer-header">
              <h2 className="kp-plan-viewer-title">Plan Viewer</h2>
            </header>
            <div className="kp-plan-viewer-body">
              <div className="kp-field">
                <div className="kp-field-label">Plan Name</div>
                <div className="kp-plan-name-field">{planName || "Untitled Test Plan"}</div>
              </div>
              <div className="kp-plan-steps-block">
                <div className="kp-plan-steps-title">Steps</div>
                <ol className="kp-plan-steps-list">
                  {stepTexts.length === 0 ? (
                    <li className="kp-plan-step-row kp-text-muted">
                      No steps defined yet.
                    </li>
                  ) : (
                    stepTexts.map((text, index) => (
                      <li key={index} className="kp-plan-step-row">
                        <div className="kp-plan-step-index">{index + 1}</div>
                        <div className="kp-plan-step-text">{text}</div>
                      </li>
                    ))
                  )}
                </ol>
              </div>
            </div>
          </section>

          <section className="kp-plan-viewer-scroll">
            <header className="kp-plan-viewer-scroll-header">
              <h3 className="kp-plan-viewer-scroll-title">
                High-Level Summary
              </h3>
            </header>
            <div className="kp-plan-viewer-scroll-body">
              <p className="kp-plan-summary-text">
                {summaryText.split("\n").map((line, idx) => (
                  <span key={idx}>
                    {line}
                    <br />
                  </span>
                ))}
              </p>
              {plan && (
                <div className="kp-plan-schema-status">
                  <span
                    className={plan.valid ? "kp-badge-ok" : "kp-badge-error"}
                  >
                    {plan.valid ? "Schema valid" : "Schema issues"}
                  </span>
                  {plan.model ? (
                    <span className="kp-plan-model">Model: {plan.model}</span>
                  ) : null}
                </div>
              )}
              {plan?.errors && plan.errors.length ? (
                <ul className="kp-plan-errors">
                  {plan.errors.map((err, index) => (
                    <li key={index}>{err}</li>
                  ))}
                </ul>
              ) : null}
              {plan ? (
                <details className="kp-plan-json-details">
                  <summary>Show raw JSON plan</summary>
                  <pre className="kp-plan-json">
                    {JSON.stringify(plan.plan, null, 2)}
                  </pre>
                </details>
              ) : null}
            </div>
          </section>
        </div>

        <div className="kp-plan-viewer-buttons">
          <button
            type="button"
            className="kp-btn kp-btn-primary"
            onClick={onRun}
          >
            Run
          </button>
          <button
            type="button"
            className="kp-btn kp-btn-secondary"
            onClick={onClose}
          >
            Edit
          </button>
          <button
            type="button"
            className="kp-btn kp-btn-secondary"
            onClick={onUpdatePreview}
          >
            Update Preview
          </button>
          <button
            type="button"
            className="kp-btn kp-btn-ghost"
            onClick={onReportIssue ?? onClose}
          >
            Report Issue
          </button>
        </div>
      </div>
    </div>
  );
};
