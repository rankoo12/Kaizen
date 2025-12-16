import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useToast } from "../components/ToastContext";

type TestSummary = {
  id: string;
  name: string;
};

type PortalTest = {
  id: string;
  name?: string;
};

type PortalSuite = {
  id: string;
  name?: string;
  tests?: string[];
};

export const CreateSuitePage = () => {
  const [suiteName, setSuiteName] = useState("");
  const [availableTests, setAvailableTests] = useState<TestSummary[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);
  const [existingSuites, setExistingSuites] = useState<PortalSuite[]>([]);
  const [selectedSuiteIdForLoad, setSelectedSuiteIdForLoad] = useState("");
  const toast = useToast();
  const navigate = useNavigate();

  useEffect(() => {
    let cancelled = false;
    const fetchTests = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch("/api/tests");
        if (!response.ok) {
          const text = await response.text();
          throw new Error(`Status ${response.status}: ${text}`);
        }
        const data: { items?: PortalTest[] } = await response.json();
        const mapped: TestSummary[] = (data.items || []).map((t) => ({
          id: String(t.id),
          name: t.name || String(t.id),
        }));
        if (!cancelled) {
          setAvailableTests(mapped);
        }
      } catch (e) {
        if (!cancelled) {
          setError(
            e instanceof Error ? e.message : "Failed to load tests.",
          );
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };
    fetchTests();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const fetchSuites = async () => {
      try {
        const response = await fetch("/api/suites");
        if (!response.ok) {
          return;
        }
        const data: { items?: PortalSuite[] } = await response.json();
        if (!cancelled) {
          setExistingSuites(
            (data.items || []).map((s) => ({
              id: String(s.id),
              name: s.name || String(s.id),
              tests: Array.isArray(s.tests) ? s.tests.map(String) : [],
            })),
          );
        }
      } catch {
        // ignore; suites list is a convenience
      }
    };
    fetchSuites();
    return () => {
      cancelled = true;
    };
  }, []);

  const addToSuite = (id: string) => {
    setSelectedIds((current) =>
      current.includes(id) ? current : [...current, id],
    );
  };

  const removeFromSuite = (id: string) => {
    setSelectedIds((current) => current.filter((x) => x !== id));
  };

  const selectedTests = useMemo(
    () =>
      selectedIds
        .map((id) => availableTests.find((t) => t.id === id))
        .filter((t): t is TestSummary => Boolean(t)),
    [selectedIds, availableTests],
  );

  const suiteId = useMemo(() => {
    const base =
      suiteName.trim().toLowerCase().replace(/\s+/g, "-") || "suite";
    return base;
  }, [suiteName]);

  const handleSaveSuite = async () => {
    if (!suiteName.trim()) {
      toast.showToast("error", "Suite name is required.");
      return;
    }
    if (!selectedIds.length) {
      toast.showToast("error", "Add at least one test to the suite.");
      return;
    }
    setSaving(true);
    try {
      const spec = {
        id: suiteId,
        name: suiteName.trim(),
        tests: selectedIds,
      };
      const response = await fetch("/api/suites", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          id: suiteId,
          spec,
        }),
      });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(`Save failed (${response.status}): ${text}`);
      }
      toast.showToast("success", "Suite saved successfully.");
    } catch (e) {
      toast.showToast(
        "error",
        e instanceof Error ? e.message : "Failed to save suite.",
      );
    } finally {
      setSaving(false);
    }
  };

  const handleRunSuite = async () => {
    if (!suiteName.trim() || !selectedIds.length) {
      await handleSaveSuite();
    }
    setRunning(true);
    try {
      const response = await fetch(
        `/api/suites/${encodeURIComponent(suiteId)}/runs`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ mode: "live" }),
        },
      );
      if (!response.ok) {
        const text = await response.text();
        throw new Error(`Run failed (${response.status}): ${text}`);
      }
      const data: { runId?: string; runIds?: string[] } = await response.json();
      const runLabel = data.runIds?.length
        ? `Run started for ${data.runIds.length} tests.`
        : data.runId
        ? `Run started (run ID: ${data.runId}).`
        : "Run started.";
      toast.showToast(
        "success",
        runLabel,
      );
      navigate("/runs");
    } catch (e) {
      toast.showToast(
        "error",
        e instanceof Error ? e.message : "Failed to run suite.",
      );
    } finally {
      setRunning(false);
    }
  };

  const handleCancel = () => {
    navigate("/tests");
  };

  return (
    <section className="kp-test-editor" aria-label="Create test suite">
      <div className="kp-test-editor-grid">
        <div className="kp-test-editor-panel">
          <div className="kp-panel-header">
            <h2 className="kp-panel-title">Create Test Suite</h2>
          </div>
          <div className="kp-panel-body">
            {existingSuites.length ? (
              <div className="kp-field">
                <label className="kp-field-label" htmlFor="existing-suite">
                  Existing Suites
                </label>
                <select
                  id="existing-suite"
                  className="kp-select"
                  value={selectedSuiteIdForLoad}
                  onChange={(event) => {
                    const value = event.target.value;
                    setSelectedSuiteIdForLoad(value);
                    const suite = existingSuites.find((s) => s.id === value);
                    if (suite) {
                      setSuiteName(suite.name || suite.id);
                      setSelectedIds(suite.tests || []);
                    }
                  }}
                >
                  <option value="">Select a suite…</option>
                  {existingSuites.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </select>
              </div>
            ) : null}

            <div className="kp-field">
              <label className="kp-field-label" htmlFor="suite-name">
                Suite Name
              </label>
              <input
                id="suite-name"
                type="text"
                className="kp-input kp-field-input"
                value={suiteName}
                onChange={(event) => setSuiteName(event.target.value)}
                placeholder="Smoke suite for login and checkout"
              />
            </div>
            <div className="kp-field">
              <div className="kp-field-label">Available Tests</div>
              {loading ? (
                <p className="kp-text-muted">Loading tests…</p>
              ) : error ? (
                <p className="kp-text-error">{error}</p>
              ) : availableTests.length === 0 ? (
                <p className="kp-text-muted">
                  No tests available yet. Create a test first.
                </p>
              ) : (
                <ul className="kp-suite-available-list">
                  {availableTests.map((t) => (
                    <li key={t.id} className="kp-suite-available-row">
                      <div className="kp-suite-available-name">{t.name}</div>
                      <button
                        type="button"
                        className="kp-btn kp-btn-secondary kp-suite-add-btn"
                        onClick={() => addToSuite(t.id)}
                      >
                        Add
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>

        <div className="kp-test-editor-panel">
          <div className="kp-panel-header">
            <h2 className="kp-panel-title">Tests in This Suite</h2>
          </div>
          <div className="kp-panel-body">
            {selectedTests.length === 0 ? (
              <p className="kp-text-muted">
                No tests added yet. Use the list on the left to add tests.
              </p>
            ) : (
              <ol className="kp-suite-selected-list">
                {selectedTests.map((t, index) => (
                  <li key={t.id} className="kp-suite-selected-row">
                    <div className="kp-step-index">{index + 1}</div>
                    <div className="kp-suite-selected-name">{t.name}</div>
                    <button
                      type="button"
                      className="kp-btn kp-btn-secondary kp-suite-remove-btn"
                      onClick={() => removeFromSuite(t.id)}
                    >
                      Remove
                    </button>
                  </li>
                ))}
              </ol>
            )}
          </div>
        </div>
      </div>

      <footer className="kp-test-editor-footer">
        <div className="kp-test-editor-footer-inner">
          <button
            type="button"
            className="kp-btn kp-btn-secondary"
            disabled={saving}
            onClick={handleSaveSuite}
          >
            {saving ? "Saving…" : "Save Suite"}
          </button>
          <button
            type="button"
            className="kp-btn kp-btn-secondary"
            onClick={handleCancel}
          >
            Cancel
          </button>
          <button
            type="button"
            className="kp-btn kp-btn-primary"
            disabled={running}
            onClick={handleRunSuite}
          >
            {running ? "Running…" : "Run Suite"}
          </button>
        </div>
      </footer>
    </section>
  );
};
