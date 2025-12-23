import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

type TestRow = {
  id: string;
  name: string;
  tags: string[];
  lastUpdated: string;
  steps: number;
  suites: string[];
};

type PortalTest = {
  id: string;
  name?: string;
  tags?: string[] | null;
  steps?: Array<{ text?: string }>;
  suites?: string[] | null;
  updatedAt?: string;
};

const formatDate = (iso: string) => {
  try {
    const date = new Date(iso);
    return date.toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return iso;
  }
};

export const TestsPage = () => {
  const [query, setQuery] = useState("");
  const [tagFilter, setTagFilter] = useState<string>("all");
  const [tests, setTests] = useState<TestRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
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
        const mapped: TestRow[] = (data.items || []).map((t) => {
          const tags = Array.isArray(t.tags)
            ? t.tags.map((tag) => String(tag))
            : [];
          const suites = Array.isArray(t.suites)
            ? t.suites.map((s) => String(s))
            : [];
          const stepsCount = Array.isArray(t.steps) ? t.steps.length : 0;
          return {
            id: String(t.id),
            name: t.name || String(t.id),
            tags,
            lastUpdated: t.updatedAt || new Date().toISOString().slice(0, 10),
            steps: stepsCount,
            suites,
          };
        });
        if (!cancelled) {
          setTests(mapped);
        }
      } catch (e) {
        if (!cancelled) {
          setError(
            e instanceof Error
              ? e.message
              : "Failed to load tests from portal.",
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

  const allTags = useMemo(() => {
    const set = new Set<string>();
    for (const t of tests) {
      for (const tag of t.tags) {
        if (tag.trim()) {
          set.add(tag.trim());
        }
      }
    }
    return Array.from(set).sort((a, b) => a.localeCompare(b));
  }, [tests]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return tests.filter((t) => {
      if (tagFilter !== "all" && !t.tags.includes(tagFilter)) {
        return false;
      }
      if (!q) {
        return true;
      }
      const haystack = [
        t.name,
        t.tags.join(", "),
        t.suites.join(", "),
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(q);
    });
  }, [tests, query, tagFilter]);

  return (
    <section className="kp-tests" aria-label="Tests">
      <div className="kp-tests-board">
        <header className="kp-tests-header">
          <div>
            <h1 className="kp-tests-title">Tests</h1>
          </div>
          <div className="kp-tests-header-actions">
            <button
              type="button"
              className="kp-btn kp-btn-primary kp-tests-create-btn"
              onClick={() => navigate("/tests/new")}
            >
              Create Test
            </button>
          </div>
        </header>

        <div className="kp-tests-toolbar">
          <div className="kp-tests-search">
            <span className="kp-tests-search-icon" aria-hidden="true">
              🔍
            </span>
            <input
              type="search"
              className="kp-input kp-tests-search-input"
              placeholder="Search by name, tag, or content"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              aria-label="Search tests by name, tag, or content"
            />
          </div>
          <div className="kp-tests-filter">
            <label className="kp-sr-only" htmlFor="tests-tag-filter">
              Filter by tag
            </label>
            <select
              id="tests-tag-filter"
              className="kp-select"
              value={tagFilter}
              onChange={(event) => setTagFilter(event.target.value)}
            >
              <option value="all">All tags</option>
              {allTags.map((tag) => (
                <option key={tag} value={tag}>
                  {tag}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="kp-tests-table-wrapper">
          {loading ? (
            <div className="kp-tests-loading kp-text-muted">
              Loading tests…
            </div>
          ) : error ? (
            <div className="kp-text-error">{error}</div>
          ) : (
            <table className="kp-table kp-tests-table" aria-label="Tests list">
              <thead>
                <tr>
                  <th scope="col">Name</th>
                  <th scope="col">Tags</th>
                  <th scope="col">Last Updated</th>
                  <th scope="col">Steps</th>
                  <th scope="col">Suites</th>
                  <th scope="col" className="kp-tests-actions-header">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((test) => (
                  <tr key={test.id}>
                    <td>{test.name}</td>
                    <td>
                      {test.tags.length ? (
                        <div className="kp-tag-row">
                          {test.tags.map((tag) => (
                            <span key={tag} className="kp-tag-pill">
                              {tag}
                            </span>
                          ))}
                        </div>
                      ) : (
                        <span className="kp-text-muted">—</span>
                      )}
                    </td>
                    <td>{formatDate(test.lastUpdated)}</td>
                    <td>{test.steps}</td>
                    <td>{test.suites.join(", ")}</td>
                    <td>
                      <div className="kp-tests-actions">
                        <button
                          type="button"
                          className="kp-icon-button"
                          aria-label={`Edit ${test.name}`}
                          onClick={() =>
                            navigate(
                              `/tests/${encodeURIComponent(test.id)}/edit`,
                            )
                          }
                        >
                          ✎
                        </button>
                        <button
                          type="button"
                          className="kp-icon-button"
                          aria-label={`Run ${test.name}`}
                        >
                          ➜
                        </button>
                        <button
                          type="button"
                          className="kp-icon-button"
                          aria-label={`Duplicate ${test.name}`}
                        >
                          ⧉
                        </button>
                        <button
                          type="button"
                          className="kp-icon-button kp-icon-button-danger"
                          aria-label={`Delete ${test.name}`}
                        >
                          ✕
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {filtered.length === 0 ? (
                  <tr>
                    <td colSpan={6}>
                      <span className="kp-text-muted">
                        No tests match your filters.
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
