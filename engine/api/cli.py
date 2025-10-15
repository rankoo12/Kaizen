import argparse
import json
from engine.core.config.container import build_container


def _load_spec(path: str):
    with open(path, "r", encoding="utf-8") as f:
        spec_data = json.load(f)

    class Step:
        def __init__(self, text):
            self.text = text

    class Spec:
        def __init__(self, id, steps):
            self.id = id
            self.steps = [Step(s["text"]) for s in steps]

    return Spec(spec_data.get("id", "test-1"), spec_data.get("steps", []))


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
        spec = _load_spec(args.spec)
        runner = container.snapshot_runner()
        run_id = runner.run(spec, html=args.html, snapshot_path=args.snapshot)
        print(f"✅ Snapshot run complete: {run_id}")
        return

    if args.command == "live-run":
        spec = _load_spec(args.spec)
        runner = container.live_runner()
        run_id = runner.run_sync(spec, url=args.url)
        print(f"✅ Live run complete: {run_id}")
        return

    print("Engine CLI skeleton OK.", args)


if __name__ == "__main__":
    main()
