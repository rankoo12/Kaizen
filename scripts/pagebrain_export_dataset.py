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
  - label_source: optional source string (e.g. healer_success, human_passed, human_failed)

When a Postgres storage backend is configured, human annotations stored in
run_action_annotations (via /api/runs/{id}/annotations) are used to adjust:
  - ok (e.g. human_failed → ok=False)
  - label_source (e.g. human_passed / human_failed)

This is a raw export; `pagebrain_curate_dataset.py` performs success gating and
train/dev splitting.
"""

from __future__ import annotations

from pathlib import Path
import json

try:
    from engine.core.storage.postgres import PostgresStorage  # type: ignore
    from engine.core.config.settings import settings as _settings  # type: ignore
except Exception:  # pragma: no cover - optional Postgres dependency
    PostgresStorage = None  # type: ignore[assignment]
    _settings = None  # type: ignore[assignment]

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


def _selector_features(sel: dict) -> dict:
    val = sel.get("value") or ""
    val_str = val if isinstance(val, str) else str(val)
    features = {
        "selector_len": float(len(val_str)),
        "has_id": 1.0 if "#" in val_str else 0.0,
        "has_class": 1.0 if "." in val_str else 0.0,
        "has_attr": 1.0 if "[" in val_str else 0.0,
        "num_desc": float(val_str.count(" ")),
        "visible": 1.0 if sel.get("visible", True) else 0.0,
        "enabled": 1.0 if sel.get("enabled", True) else 0.0,
    }
    sel_type = sel.get("type")
    features["type_is_css"] = 1.0 if sel_type == "css" else 0.0
    features["type_is_xpath"] = 1.0 if isinstance(sel_type, str) and "xpath" in sel_type.lower() else 0.0
    return features


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
                    "features": _selector_features(sel),
                }
            )
    return candidates, len(candidates)


_PG_ANNOT_STORAGE: PostgresStorage | None = None


def _get_pg_storage_for_annotations() -> PostgresStorage | None:
    """Best-effort PostgresStorage for annotation lookup (optional).

    When Postgres is not configured, returns None so export remains file-only.
    """
    global _PG_ANNOT_STORAGE
    if _PG_ANNOT_STORAGE is not None:
        return _PG_ANNOT_STORAGE
    if PostgresStorage is None or _settings is None:  # type: ignore[truthy-function]
        return None
    try:
        dsn = getattr(_settings, "PG_DSN", None)
        backend = getattr(_settings, "STORAGE_BACKEND", "auto")
    except Exception:
        dsn = None
        backend = "auto"
    use_pg = bool(dsn) and str(backend) in {"auto", "postgres"}
    if not use_pg:
        return None
    try:
        _PG_ANNOT_STORAGE = PostgresStorage(str(dsn))
    except Exception:
        _PG_ANNOT_STORAGE = None
    return _PG_ANNOT_STORAGE


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    out_path = REPORTS / "pagebrain_dataset.jsonl"
    total = 0

    # Optional annotation cache: run_id -> (action_index -> annotation dict)
    ann_cache: dict[str, dict[int, dict]] = {}

    def _ann_for(run_id: str, action_index: int) -> dict | None:
        st = _get_pg_storage_for_annotations()
        if st is None:
            return None
        rid = str(run_id)
        if rid not in ann_cache:
            mapping: dict[int, dict] = {}
            try:
                rows = st.get_run_action_annotations(rid)  # type: ignore[attr-defined]
            except Exception:
                rows = []
            for ann in rows or []:
                idx = ann.get("action_index")
                if not isinstance(idx, int):
                    continue
                existing = mapping.get(idx)
                # Prefer explicit human_truth annotations when multiple sources exist
                if existing is not None and (existing.get("source") == "human_truth"):
                    continue
                mapping[idx] = ann
            ann_cache[rid] = mapping
        try:
            return ann_cache[rid].get(int(action_index))
        except Exception:
            return None

    with out_path.open("w", encoding="utf-8") as fp:
        for fname, rec in _iter_action_events():
            run_id = rec.get("run_id") or fname.replace("run-", "").replace(".jsonl", "")
            tool = rec.get("tool")
            raw_pb = rec.get("pagebrain")
            pb = raw_pb if isinstance(raw_pb, dict) else {}
            chosen_sel = _norm_selector((pb.get("chosen") or {}).get("selector"))
            candidates, cand_count = _norm_candidates(pb)
            if not candidates and chosen_sel:
                candidates = [{
                    "selector": chosen_sel,
                    "rank": 0,
                    "visible": chosen_sel.get("visible"),
                    "enabled": chosen_sel.get("enabled"),
                    "features": _selector_features(chosen_sel),
                }]
                cand_count = 1
            label_idx = None
            if chosen_sel and candidates:
                for i, c in enumerate(candidates):
                    sel = c.get("selector") or {}
                    if sel.get("type") == chosen_sel.get("type") and sel.get("value") == chosen_sel.get("value"):
                        label_idx = i
                        break
            label_source = pb.get("label_source")

            # Base success signal from executor/logs
            ok_flag = bool(rec.get("executor", {}).get("status") == "passed") or bool(rec.get("ok", False))

            # Optional human annotation overlay (passed/failed per action)
            action_index = rec.get("action_index")
            try:
                action_index_int = int(action_index)
            except Exception:
                action_index_int = None
            annotation = None
            if action_index_int is not None:
                annotation = _ann_for(run_id, action_index_int)
                if annotation is not None:
                    ann_label = (annotation.get("label") or "").strip().lower()
                    ann_source = annotation.get("source") or "human_truth"
                    # Treat explicit human "failed" as overriding success gating
                    if ann_label == "failed":
                        ok_flag = False
                        label_source = "human_failed"
                    elif ann_label == "passed":
                        label_source = "human_passed"
            example = {
                "example_id": f"{run_id}-{total}",
                "run_id": run_id,
                "tool": tool,
                "ok": ok_flag,
                "reason": rec.get("reason"),
                "target_signature": rec.get("target_signature") or rec.get("executor", {}).get("signature"),
                "pagebrain": pb,
                "perception": rec.get("perception") or {},
                "candidates": candidates,
                "label": label_idx,
                "candidate_count": cand_count,
                "label_source": label_source,
            }
            fp.write(json.dumps(example, ensure_ascii=False) + "\n")
            total += 1
    print(f"wrote {total} pagebrain examples to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
