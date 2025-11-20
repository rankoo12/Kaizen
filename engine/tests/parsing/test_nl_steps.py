from engine.core.parsing.nl_steps import parse_steps_text


def test_parse_steps_text_basic():
    text = """
click Login
# comment
  type hello

press Enter
"""
    steps = parse_steps_text(text)
    # Preserve original text order
    assert [s.get("text") for s in steps] == [
        "click Login",
        "type hello",
        "press Enter",
    ]
    # Ensure contract-style ids and indices are present and stable
    assert [s.get("index") for s in steps] == [1, 2, 3]
    assert [s.get("id") for s in steps] == ["step_1", "step_2", "step_3"]
