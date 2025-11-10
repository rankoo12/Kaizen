from __future__ import annotations

from engine.core.parsing.keys import normalize_key_name


def test_normalize_basic_keys():
    assert normalize_key_name("enter") == "Enter"
    assert normalize_key_name("ESC") == "Escape"
    assert normalize_key_name("tab") == "Tab"
    assert normalize_key_name("space") == "Space"


def test_normalize_arrows():
    assert normalize_key_name("left") == "ArrowLeft"
    assert normalize_key_name("arrowright") == "ArrowRight"
    assert normalize_key_name("Up") == "ArrowUp"
    assert normalize_key_name("downarrow") == "ArrowDown"


def test_normalize_chords():
    assert normalize_key_name("ctrl+a") == "Control+A"
    assert normalize_key_name("Control + a") == "Control+A"
    assert normalize_key_name("cmd+a") == "Meta+A"
    assert normalize_key_name("shift+Enter") == "Shift+Enter"
