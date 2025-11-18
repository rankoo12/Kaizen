from engine.eval.harness import default_corpus, run_snapshot_case


def test_default_corpus_has_categories_and_min_size():
    corpus = default_corpus()
    # Guardrail: corpus should not shrink silently
    assert len(corpus) >= 15
    categories = {c.category for c in corpus}
    for c in corpus:
        assert isinstance(c.case_id, str) and c.case_id
        assert isinstance(c.category, str) and c.category
    # Ensure key categories stay represented as we evolve the corpus
    for required in {"controls", "dialogs", "lists", "forms"}:
        assert required in categories


def test_run_snapshot_case_is_stable_for_corpus():
    corpus = default_corpus()
    for case in corpus:
        ok, meta = run_snapshot_case(case)
        assert isinstance(ok, bool)
        assert isinstance(meta, dict)
