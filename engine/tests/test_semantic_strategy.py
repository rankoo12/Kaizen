from engine.core.resolving.strategies.semantic import SemanticStrategy


def test_semantic_strategy_ranks_role_and_text():
    strat = SemanticStrategy()
    catalog = [
        {
            "tag": "button",
            "role": "button",
            "text": "Sign in",
            "visible": True,
            "clickable": True,
        },
        {
            "tag": "a",
            "role": "link",
            "text": "Sign in",
            "visible": True,
            "clickable": True,
        },
        {
            "tag": "button",
            "role": "button",
            "text": "Register",
            "visible": True,
            "clickable": True,
        },
    ]
    query = {"text": "Sign in", "hints": {"role": "button"}}
    scored = strat.score(query, catalog)
    assert scored[0][0]["text"] == "Sign in" and scored[0][0]["role"] == "button"
