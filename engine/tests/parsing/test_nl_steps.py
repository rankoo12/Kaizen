from engine.core.parsing.nl_steps import parse_steps_text


def test_parse_steps_text_basic():
    text = """
click Login
# comment
  type hello

press Enter
"""
    steps = parse_steps_text(text)
    assert steps == [{"text": "click Login"}, {"text": "type hello"}, {"text": "press Enter"}]
