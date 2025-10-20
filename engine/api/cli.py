import argparse
import json
from pathlib import Path
from engine.core.config.container import build_container
from engine.core.metrics.collector import time_run


def _load_spec(path: str):
    """Load a JSON TestSpec and return an object with attributes.

    Both SnapshotRunner and LiveRunner support attribute-based access.
    We normalize steps to lightweight objects with a `.text` attribute.
    """
    with open(path, "r", encoding="utf-8") as f:
        spec_data = json.load(f)

    class Step:
        def __init__(self, text: str):
            self.text = text

    class Spec:
        def __init__(self, suite, name, id, steps):
            self.suite = suite
            self.name = name
            self.id = id
            self.steps = [Step(s) for s in steps]

    # Normalize steps text from dicts or bare strings
    step_texts = []
    for s in spec_data.get("steps", []):
        if isinstance(s, dict):
            text = s.get("text") or s.get("action") or ""
            step_texts.append(str(text))
        else:
            step_texts.append(str(s))

    suite = spec_data.get("suite") or spec_data.get("project")
    name = spec_data.get("name") or spec_data.get("title") or spec_data.get("id")
    test_id = spec_data.get("id", "test-1")

    return Spec(suite=suite, name=name, id=test_id, steps=step_texts)


@time_run
def _snapshot_run(container, args) -> str:
    spec = _load_spec(args.spec)
    runner = container.snapshot_runner()
    html_arg = args.html
    html_kw = {}
    if html_arg:
        p = Path(html_arg)
        if p.exists() and p.is_file():
            html_kw["html_path"] = str(p)
        else:
            html_kw["html"] = html_arg  # treat as inline HTML string
    return runner.run(spec, snapshot_path=args.snapshot, **html_kw)


@time_run
def _live_run(container, args) -> str:
    spec = _load_spec(args.spec)
    runner = container.live_runner()
    return runner.run_sync(spec, url=args.url)


def main():
    parser = argparse.ArgumentParser(
        prog="kaizen-engine", description="Kaizen Engine CLI"
    )
    subparsers = parser.add_subparsers(dest="command")

    # legacy flag (kept for now)
    parser.add_argument("--run", help="Run a TestSpec by id")

    # snapshot-run
    snap_parser = subparsers.add_parser(
        "snapshot-run", help="Run orchestrator in snapshot mode"
    )
    snap_parser.add_argument("spec", help="Path to TestSpec JSON file")
    snap_parser.add_argument("--html", help="Path to HTML snapshot", required=False)
    snap_parser.add_argument(
        "--snapshot", help="Path to snapshot file (optional)", required=False
    )

    # live-run
    live_parser = subparsers.add_parser(
        "live-run", help="Run orchestrator in live browser mode"
    )
    live_parser.add_argument("spec", help="Path to TestSpec JSON file")
    live_parser.add_argument(
        "--url", help="Page URL or file path (optional)", required=False
    )

    args = parser.parse_args()
    container = build_container()

    if args.command == "snapshot-run":
        run_id = _snapshot_run(container, args)
        print(f"[OK] Snapshot run complete: {run_id}")
        return

    if args.command == "live-run":
        run_id = _live_run(container, args)
        print(f"[OK] Live run complete: {run_id}")
        return

    print("Engine CLI skeleton OK.", args)


if __name__ == "__main__":
    main()
