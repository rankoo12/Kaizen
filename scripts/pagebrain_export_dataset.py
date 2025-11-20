"""
Export PageBrain choice events into a raw dataset JSONL.

Reads run-*.jsonl logs that contain `action.run` events emitted by the
executor (with PageBrain metadata). Produces:

- reports/pagebrain_dataset.jsonl

Each line includes:
  - example_id (derived from run_id + index)
  - run_id
  - tool
  - ok / reason
  - target_signature (if present)
  - pagebrain {chosen, candidates, candidate_count, path, reason}
  - label: index of the correct candidate (matched by selector)
  - candidates: normalized list of selector feature dicts

This is a raw export; `pagebrain_curate_dataset.py` performs success gating and
train/dev splitting.
"""

from __future__ import annotations

from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "logs"
REPORTS = ROOT / "reports"


def _iter_action_events():
    for path in LOGS.glob("run-*.jsonl"):
        with path.open("r", encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if not isinstance(rec, dict):
                    continue
                if rec.get("event") != "action.run":
                    continue
                yield path.name, rec


def _norm_selector(sel: dict | None) -> dict | None:
    if not isinstance(sel, dict):
        return None
    sel_type = sel.get("type")
    sel_val = sel.get("value")
    if not isinstance(sel_type, str) or not isinstance(sel_val, str):
        return None
    return {
        "type": sel_type,
        "value": sel_val,
        "visible": sel.get("visible", True),
        "enabled": sel.get("enabled", True),
    }


def _norm_candidates(pb: dict) -> tuple[list[dict], int]:
    candidates = []
    raw_cands = pb.get("candidates") if isinstance(pb, dict) else None
    if isinstance(raw_cands, list):
        for c in raw_cands:
            if not isinstance(c, dict):
                continue
            sel = _norm_selector((c.get("selector") or {}))
            if sel is None:
                continue
            candidates.append(
                {
                    "selector": sel,
                    "rank": c.get("rank"),
                    "visible": sel.get("visible"),
                    "enabled": sel.get("enabled"),
                }
            )
    return candidates, len(candidates)


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    out_path = REPORTS / "pagebrain_dataset.jsonl"
    total = 0
    with out_path.open("w", encoding="utf-8") as fp:
        for fname, rec in _iter_action_events():
            run_id = rec.get("run_id") or fname.replace("run-", "").replace(".jsonl", "")
            tool = rec.get("tool")
            pb = rec.get("pagebrain") or {}
            chosen_sel = _norm_selector((pb.get("chosen") or {}).get("selector"))
            candidates, cand_count = _norm_candidates(pb)
            if not candidates and chosen_sel:
                candidates = [{"selector": chosen_sel, "rank": 0, "visible": chosen_sel.get("visible"), "enabled": chosen_sel.get("enabled")}]
                cand_count = 1
            label_idx = None
            if chosen_sel and candidates:
                for i, c in enumerate(candidates):
                    sel = c.get("selector") or {}
                    if sel.get("type") == chosen_sel.get("type") and sel.get("value") == chosen_sel.get("value"):
                        label_idx = i
                        break
            example = {
                "example_id": f"{run_id}-{total}",
                "run_id": run_id,
                "tool": tool,
                "ok": bool(rec.get("executor", {}).get("status") == "passed") or bool(rec.get("ok", False)),
                "reason": rec.get("reason"),
                "target_signature": rec.get("target_signature") or rec.get("executor", {}).get("signature"),
                "pagebrain": pb,
                "candidates": candidates,
                "label": label_idx,
                "candidate_count": cand_count,
            }
            fp.write(json.dumps(example, ensure_ascii=False) + "\n")
            total += 1
    print(f"wrote {total} pagebrain examples to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
