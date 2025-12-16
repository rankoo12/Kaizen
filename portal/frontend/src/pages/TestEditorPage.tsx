import type { FormEvent, KeyboardEvent } from "react";
import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { PlanPreviewModal } from "../components/PlanPreviewModal";
import { useToast } from "../components/ToastContext";

type VariableRow = {
  id: string;
  key: string;
  value: string;
};

type StepRow = {
  id: string;
  text: string;
  timeoutMs?: number;
  expected?: string;
};

type PlanPreview = {
  plan: unknown;
  valid: boolean;
  errors: string[];
  model?: string | null;
};

const createEmptyStep = (index: number): StepRow => ({
  id: `step-${index}`,
  text: "",
});

const deriveAppBaseUrlFromSteps = (steps: StepRow[]): string | undefined => {
  for (const step of steps) {
    const text = step.text.trim();
    if (!text) continue;
    const lower = text.toLowerCase();
    if (!lower.startsWith("open ")) continue;
    const rest = text.slice(5).trim();
    if (!rest) continue;
    const candidate = rest.split(/\s+/)[0];
    if (/^(https?:|about:|data:)/i.test(candidate)) {
      return candidate;
    }
  }
  return undefined;
};

export const TestEditorPage = () => {
  const { testId: routeTestId } = useParams<{ testId: string }>();
  const navigate = useNavigate();

  const [testId, setTestId] = useState<string | null>(routeTestId ?? null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [tagInput, setTagInput] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const [variables, setVariables] = useState<VariableRow[]>([]);
  const [varKey, setVarKey] = useState("");
  const [varValue, setVarValue] = useState("");
  const [steps, setSteps] = useState<StepRow[]>([
    createEmptyStep(1),
    createEmptyStep(2),
    createEmptyStep(3),
  ]);
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [preview, setPreview] = useState<PlanPreview | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { showToast } = useToast();
  const isEditMode = routeTestId != null;

  const urlFromVariables = useMemo(() => {
    const row = variables.find((v) => v.key.toLowerCase().trim() === "url");
    return row?.value ?? "";
  }, [variables]);

  const normalizedTags = useMemo(
    () => tags.map((t) => t.trim()).filter(Boolean),
    [tags],
  );

  const addTagFromInput = () => {
    const raw = tagInput.trim();
    if (!raw) return;
    if (!normalizedTags.includes(raw)) {
      setTags((current) => [...current, raw]);
    }
    setTagInput("");
  };

  const removeTag = (tag: string) => {
    setTags((current) => current.filter((t) => t !== tag));
  };

  const onTagKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      event.preventDefault();
      addTagFromInput();
    } else if (event.key === "Backspace" && !tagInput && tags.length) {
      setTags((current) => current.slice(0, -1));
    }
  };

  const addVariable = () => {
    const key = varKey.trim();
    const value = varValue.trim();
    if (!key || !value) return;
    setVariables((current) => [
      ...current,
      { id: `var-${Date.now()}-${current.length + 1}`, key, value },
    ]);
    setVarKey("");
    setVarValue("");
  };

  const removeVariable = (id: string) => {
    setVariables((current) => current.filter((v) => v.id !== id));
  };

  const updateStep = (id: string, patch: Partial<StepRow>) => {
    setSteps((current) =>
      current.map((s) => (s.id === id ? { ...s, ...patch } : s)),
    );
  };

  const addStepBelow = () => {
    setSteps((current) => {
      const nextIndex = current.length + 1;
      return [...current, createEmptyStep(nextIndex)];
    });
  };

  const moveStep = (id: string, direction: "up" | "down") => {
    setSteps((current) => {
      const index = current.findIndex((s) => s.id === id);
      if (index === -1) return current;
      const targetIndex = direction === "up" ? index - 1 : index + 1;
      if (targetIndex < 0 || targetIndex >= current.length) return current;
      const next = [...current];
      const [item] = next.splice(index, 1);
      next.splice(targetIndex, 0, item);
      return next;
    });
  };

  const deleteStep = (id: string) => {
    setSteps((current) => {
      if (current.length <= 1) return current;
      return current.filter((s) => s.id !== id);
    });
  };

  const duplicateStep = (id: string) => {
    setSteps((current) => {
      const index = current.findIndex((s) => s.id === id);
      if (index === -1) return current;
      const source = current[index];
      const copy: StepRow = {
        ...source,
        id: `step-${Date.now()}-${index}`,
      };
      const next = [...current];
      next.splice(index + 1, 0, copy);
      return next;
    });
  };

  const buildTestSpec = () => {
    const baseSlug =
      name.trim().toLowerCase().replace(/\s+/g, "-") || "test";
    // In create mode, always generate a fresh id so saving multiple
    // tests in a row creates separate tests. In edit mode, keep the
    // existing id stable.
    const id =
      testId ||
      (isEditMode && routeTestId) ||
      `${baseSlug}-${Date.now().toString(36)}`;
    const vars: Record<string, string> = {};
    for (const row of variables) {
      const key = row.key.trim();
      if (key) {
        vars[key] = row.value;
      }
    }
    const trimmedSteps = steps
      .map((s, index) => ({
        id: s.id,
        index: index + 1,
        text: s.text.trim(),
        timeout: s.timeoutMs,
        expected: s.expected,
      }))
      .filter((s) => s.text.length);
    const appBaseUrl =
      urlFromVariables || deriveAppBaseUrlFromSteps(steps) || "about:blank";
    return {
      id,
      name: name || id,
      description: description || undefined,
      tags: normalizedTags,
      vars,
      app_base_url: appBaseUrl,
      steps: trimmedSteps,
    };
  };

  const handleSave = async (event?: FormEvent): Promise<string | null> => {
    if (event) {
      event.preventDefault();
    }
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const spec = buildTestSpec();
      const response = await fetch("/api/tests", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(spec),
      });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(`Save failed (${response.status}): ${text}`);
      }
      const data: { testId?: string | number } = await response.json();
      const newId = (data.testId && String(data.testId)) || spec.id;
      // When editing an existing test, keep track of its id so further
      // saves update the same test. In create mode (/tests/new), each
      // save should create a new test so we intentionally do *not*
      // persist testId across saves.
      if (isEditMode) {
        setTestId(newId);
      }
      setMessage("Test saved successfully.");
      showToast("success", "Saved successfully.");
      return newId;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save test.");
      return null;
    } finally {
      setSaving(false);
    }
  };

  const handleRunTest = async () => {
    setRunning(true);
    setError(null);
    setMessage(null);
    try {
      let id = testId;
      if (!id) {
        id = await handleSave();
      }
      if (!id) {
        throw new Error("Test ID is missing after save.");
      }
      const body: Record<string, unknown> = {
        mode: "live",
        url: urlFromVariables
          || deriveAppBaseUrlFromSteps(steps)
          || "about:blank",
      };
      const response = await fetch(
        `/api/tests/${encodeURIComponent(id)}/runs`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(body),
        },
      );
      if (!response.ok) {
        const text = await response.text();
        throw new Error(`Run failed (${response.status}): ${text}`);
      }
      const data: { runId?: string } = await response.json();
      setMessage(
        data.runId
          ? `Run started (run ID: ${data.runId}).`
          : "Run started.",
      );
      showToast("success", "Run started.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start run.");
    } finally {
      setRunning(false);
    }
  };

  const handlePreviewPlan = async () => {
    const joined = steps
      .map((s, index) => `${index + 1}. ${s.text.trim()}`)
      .filter(Boolean)
      .join("\n");
    if (!joined) {
      setError("Add at least one step before previewing the plan.");
      return;
    }
    setPreviewing(true);
    setError(null);
    setMessage(null);
    try {
      const response = await fetch("/api/plan/preview", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          text: joined,
          context: urlFromVariables ? { url: urlFromVariables } : {},
        }),
      });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(`Preview failed (${response.status}): ${text}`);
      }
      const data: PlanPreview = await response.json();
      setPreview(data);
      setPreviewOpen(true);
      showToast("info", "Plan preview ready.");
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Failed to preview plan.",
      );
      setPreview(null);
      setPreviewOpen(false);
      showToast("error", "Error occurred while previewing plan.");
    } finally {
      setPreviewing(false);
    }
  };

  return (
    <section className="kp-test-editor" aria-label="Test editor">
      <div className="kp-test-editor-grid">
        <form
          className="kp-test-editor-panel kp-test-editor-meta"
          onSubmit={handleSave}
        >
          <header className="kp-panel-header">
            <h2 className="kp-panel-title">Test Metadata</h2>
          </header>
          <div className="kp-panel-body">
            <div className="kp-field">
              <label className="kp-field-label" htmlFor="test-name">
                Test Name
              </label>
              <input
                id="test-name"
                type="text"
                className="kp-input kp-field-input"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Login flow for example.com"
              />
            </div>

            <div className="kp-field">
              <label className="kp-field-label" htmlFor="test-description">
                Description
              </label>
              <textarea
                id="test-description"
                className="kp-textarea kp-field-input"
                rows={3}
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="Describe what this test covers."
              />
            </div>

            <div className="kp-field">
              <label className="kp-field-label" htmlFor="test-tags">
                Tags
              </label>
              <div className="kp-tag-input">
                {normalizedTags.map((tag) => (
                  <button
                    type="button"
                    key={tag}
                    className="kp-tag-pill kp-tag-pill-removable"
                    onClick={() => removeTag(tag)}
                  >
                    {tag}
                    <span aria-hidden="true"> ✕</span>
                  </button>
                ))}
                <input
                  id="test-tags"
                  className="kp-tag-input-inner"
                  placeholder="Add tag and press Enter"
                  value={tagInput}
                  onChange={(event) => setTagInput(event.target.value)}
                  onKeyDown={onTagKeyDown}
                />
              </div>
            </div>

            <div className="kp-field">
              <div className="kp-field-label">Variables</div>
              <div className="kp-variables-grid">
                <input
                  type="text"
                  className="kp-input kp-field-input"
                  placeholder="key (e.g. url)"
                  value={varKey}
                  onChange={(event) => setVarKey(event.target.value)}
                />
                <input
                  type="text"
                  className="kp-input kp-field-input"
                  placeholder="value"
                  value={varValue}
                  onChange={(event) => setVarValue(event.target.value)}
                />
                <button
                  type="button"
                  className="kp-btn kp-btn-secondary kp-variables-add"
                  onClick={addVariable}
                >
                  Add Variable
                </button>
              </div>
              {variables.length ? (
                <ul className="kp-variables-list">
                  {variables.map((v) => (
                    <li key={v.id} className="kp-variables-row">
                      <span className="kp-variables-key">{v.key}</span>
                      <span className="kp-variables-value">{v.value}</span>
                      <button
                        type="button"
                        className="kp-icon-button kp-icon-button-danger"
                        onClick={() => removeVariable(v.id)}
                        aria-label={`Remove variable ${v.key}`}
                      >
                        ✕
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          </div>
        </form>

        <div className="kp-test-editor-panel kp-test-editor-steps">
          <header className="kp-panel-header">
            <h2 className="kp-panel-title">Steps</h2>
          </header>
          <div className="kp-panel-body kp-steps-body">
            <ol className="kp-steps-list">
              {steps.map((step, index) => (
                <li key={step.id} className="kp-step-row">
                  <div className="kp-step-index">{index + 1}</div>
                  <div className="kp-step-main">
                    <textarea
                      className="kp-textarea kp-step-text"
                      rows={2}
                      value={step.text}
                      placeholder='Type a step, e.g. "Open https://example.com/login"'
                      onChange={(event) =>
                        updateStep(step.id, { text: event.target.value })
                      }
                    />
                    <details className="kp-step-advanced">
                      <summary>Advanced</summary>
                      <div className="kp-step-advanced-body">
                        <label className="kp-step-advanced-field">
                          <span>Timeout (ms)</span>
                          <input
                            type="number"
                            className="kp-input kp-field-input"
                            value={
                              step.timeoutMs !== undefined ? step.timeoutMs : ""
                            }
                            onChange={(event) =>
                              updateStep(step.id, {
                                timeoutMs:
                                  event.target.value === ""
                                    ? undefined
                                    : Number(event.target.value),
                              })
                            }
                          />
                        </label>
                        <label className="kp-step-advanced-field">
                          <span>Expected assertion text</span>
                          <input
                            type="text"
                            className="kp-input kp-field-input"
                            value={step.expected ?? ""}
                            onChange={(event) =>
                              updateStep(step.id, {
                                expected:
                                  event.target.value || undefined,
                              })
                            }
                          />
                        </label>
                      </div>
                    </details>
                  </div>
                  <div className="kp-step-actions">
                    <button
                      type="button"
                      className="kp-icon-button"
                      aria-label={`Move step ${index + 1} up`}
                      onClick={() => moveStep(step.id, "up")}
                    >
                      ↑
                    </button>
                    <button
                      type="button"
                      className="kp-icon-button"
                      aria-label={`Move step ${index + 1} down`}
                      onClick={() => moveStep(step.id, "down")}
                    >
                      ↓
                    </button>
                    <button
                      type="button"
                      className="kp-icon-button"
                      aria-label={`Duplicate step ${index + 1}`}
                      onClick={() => duplicateStep(step.id)}
                    >
                      ⧉
                    </button>
                    <button
                      type="button"
                      className="kp-icon-button kp-icon-button-danger"
                      aria-label={`Delete step ${index + 1}`}
                      onClick={() => deleteStep(step.id)}
                    >
                      ✕
                    </button>
                  </div>
                </li>
              ))}
            </ol>
            <div className="kp-step-add-row">
              <button
                type="button"
                className="kp-btn kp-btn-secondary"
                onClick={addStepBelow}
              >
                Add Step
              </button>
            </div>
          </div>
        </div>
      </div>

      <footer className="kp-test-editor-footer">
        <div className="kp-test-editor-footer-inner">
          <button
            type="button"
            className="kp-btn kp-btn-secondary"
            disabled={saving}
            onClick={handleSave}
          >
            {saving ? "Saving..." : "Save"}
          </button>
          <button
            type="button"
            className="kp-btn kp-btn-primary"
            disabled={running}
            onClick={handleRunTest}
          >
            {running ? "Running..." : "Run Test"}
          </button>
          <button
            type="button"
            className="kp-btn kp-btn-secondary"
            disabled={previewing}
            onClick={handlePreviewPlan}
          >
            {previewing ? "Previewing..." : "Preview Plan (LLM Dry Run)"}
          </button>
          <button
            type="button"
            className="kp-btn kp-btn-ghost"
            onClick={() => navigate("/tests")}
          >
            Back to Tests
          </button>
        </div>
        {(message || error) && (
          <div className="kp-test-editor-status">
            {message ? (
              <div className="kp-toast kp-toast-success">{message}</div>
            ) : null}
            {error ? (
              <div className="kp-toast kp-toast-error">{error}</div>
            ) : null}
          </div>
        )}
      </footer>
      <PlanPreviewModal
        open={previewOpen}
        plan={preview}
        planName={name || "Untitled Test Plan"}
        stepTexts={steps.map((s) => s.text.trim()).filter(Boolean)}
        onClose={() => setPreviewOpen(false)}
        onRun={handleRunTest}
        onUpdatePreview={handlePreviewPlan}
      />
    </section>
  );
};
