from pathlib import Path

from engine.core.healing.selector_healer import DeterministicHealer
from engine.eval.healer_retrieval import (
    HealerEvalCase,
    default_corpus,
    run_healer_case,
    aggregate,
    run_corpus,
    write_reports,
)


def test_default_healer_corpus_paths():
    healer = DeterministicHealer(storage=None)
    corpus = default_corpus()
    results = []
    for case in corpus:
        ok, meta = run_healer_case(healer, case)
        results.append((case, ok, meta))
        # Every case should at least produce a primary locator
        assert isinstance(meta.get("primary"), dict)
        assert meta["primary"].get("value")
    summary = aggregate(results)
    assert summary["total"] == len(corpus)
    assert summary["passed"] == len(corpus)
    assert "by_category" in summary and "by_reason" in summary


def test_retrieval_path_can_be_exercised_with_fake_storage():
    class _FakeStorage:
        def __init__(self):
            self.calls = 0

        def retrieve_embedding_selector(self, **kwargs):
            self.calls += 1
            return {"type": "css", "value": "#retrieved"}

    storage = _FakeStorage()
    healer = DeterministicHealer(storage=storage)
    case = HealerEvalCase(
        case_id="retrieval_case",
        category="retrieval",
        failure={"target": {"text": "Login"}},
        context={"tool": "click", "domain": "example.com", "tenant_id": "t1"},
        expect_reason="retrieval_hit",
    )
    ok, meta = run_healer_case(healer, case)
    assert ok is True
    assert meta["reason"] == "retrieval_hit"
    assert meta["primary"]["type"] == "css"
    assert meta["primary"]["value"] == "#retrieved"
    assert storage.calls >= 1


def test_run_corpus_and_write_reports(tmp_path: Path):
    healer = DeterministicHealer(storage=None)
    summary, results = run_corpus(healer)
    assert summary["total"] == len(default_corpus())
    out_dir = tmp_path / "reports"
    write_reports(summary, results, out_dir=out_dir)
    json_path = out_dir / "healer_eval_summary.json"
    csv_path = out_dir / "healer_eval_summary.csv"
    assert json_path.exists()
    assert csv_path.exists()
    content = json_path.read_text(encoding="utf-8")
    assert '"total"' in content
