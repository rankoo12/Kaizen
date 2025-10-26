#!/usr/bin/env python
import os
import sys
import time
import subprocess
import json

try:
    import httpx
except Exception:
    print(
        ">> ERROR: httpx not installed. Ensure requirements.txt is installed before running ci_sanity.",
        file=sys.stderr,
    )
    sys.exit(2)


def wait_for(url: str, timeout: float = 20.0) -> bool:
    start = time.time()
    while (time.time() - start) < timeout:
        try:
            r = httpx.get(url, timeout=2.0)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def main() -> int:
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    env.setdefault("PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD", "1")

    # Start engine-api in background (factory mode uses create_app())
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "engine.api.server:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            "8080",
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        ok = wait_for("http://127.0.0.1:8080/api/healthz", timeout=25.0)
        if not ok:
            print(
                ">> ERROR: engine-api did not become healthy in time", file=sys.stderr
            )
            return 1

        payload = {
            "mode": "snapshot",
            "spec": {
                "suite": "ci",
                "name": "smoke",
                "id": "sample",
                "steps": [{"text": "press Enter"}],
            },
            "html": "<html><body><button id='ok'>OK</button></body></html>",
        }
        with httpx.Client(timeout=10.0) as client:
            r = client.post("http://127.0.0.1:8080/api/runs", json=payload)
            if r.status_code != 200:
                print(
                    f">> ERROR: POST /api/runs failed: {r.status_code} {r.text}",
                    file=sys.stderr,
                )
                return 1
            run_id = r.json().get("run_id")
            if not run_id:
                print(
                    ">> ERROR: No run_id returned from /api/runs",
                    file=sys.stderr,
                )
                return 1

            # Poll for status (finished or running acceptable, but prefer finished)
            status = None
            stats = None
            for _ in range(40):
                g = client.get(f"http://127.0.0.1:8080/api/runs/{run_id}")
                if g.status_code != 200:
                    time.sleep(0.5)
                    continue
                body = g.json()
                status = body.get("status")
                stats = body.get("stats")
                if status == "finished":
                    break
                time.sleep(0.5)

            if status not in {"finished", "running"}:
                print(f">> ERROR: Unexpected run status: {status}", file=sys.stderr)
                return 1

            if not isinstance(stats, dict):
                print(f">> ERROR: Missing stats in run payload: {stats}", file=sys.stderr)
                return 1

            # Assert minimal keys present to guard regressions
            required = {"planner", "heal_attempts", "healed_rate"}
            if not required.issubset(set(stats.keys())):
                print(f">> ERROR: Missing required stats keys: {required - set(stats.keys())}", file=sys.stderr)
                return 1

            print(">> OK: CI sanity run passed", json.dumps({"run_id": run_id, "status": status}))
            return 0
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
