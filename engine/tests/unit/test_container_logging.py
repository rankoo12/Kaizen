import json
from pathlib import Path

from engine.core.config.container import build_container
from engine.core.logging.log import JsonlLogger
from engine.core.config import settings as settings_mod


def test_di_wires_jsonl_logger_and_writes_jsonl(tmp_path, monkeypatch):
    """
    Verifies:
    1) DI container returns a JsonlLogger implementation for logger.
    2) A call to logger.info() produces a JSONL file in LOGS_DIR.
    """

    # Redirect logs directory to a temp folder for this test (no repo pollution)
    monkeypatch.setattr(settings_mod.settings, "LOGS_DIR", Path(tmp_path), raising=True)

    c = build_container()
    logger = c.logger()

    # Type check: DI returns our JsonlLogger (implementation detail OK to assert)
    assert isinstance(logger, JsonlLogger)

    # Action: write one info event
    logger.info("unit_test_event", foo=123, ok=True)

    # Assert: at least one JSONL file was created in tmp_path
    jsonl_files = list(Path(tmp_path).glob("*.jsonl"))
    assert jsonl_files, "Expected at least one *.jsonl file to be written"

    # Read the last written file and check the last line is valid JSON with keys
    last_file = sorted(jsonl_files)[-1]
    last_line = last_file.read_text(encoding="utf-8").strip().splitlines()[-1]
    record = json.loads(last_line)

    assert record.get("level") == "INFO"
    assert record.get("msg") == "unit_test_event"
    # Basic shape keys that should exist
    for k in ("ts", "run_id"):
        assert k in record
