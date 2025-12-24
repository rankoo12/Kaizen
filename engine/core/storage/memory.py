from __future__ import annotations


class InMemoryStorage:
    def __init__(self) -> None:
        self._runs: dict[str, dict] = {}
        # profiles: list of dicts with keys: domain, tool, target_signature, selector, hits, last_seen
        self._profiles: list[dict] = []
        # per-action annotations for runs (dev-only, in-memory)
        self._annotations: list[dict] = []

    def start_run(self, test_id):
        import time as _time

        # Use timestamp-based suffix to avoid reusing the same run_id
        # across multiple executions of the same test (e.g., contract tests).
        ts = int(_time.time())
        rid = f"run-{ts}-{test_id}"
        self._runs[rid] = {"test_id": test_id, "started": True, "started_at": ts}
        return rid

    def record_step(self, step):
        return None

    def finish_run(self, run_id, stats: dict | None = None):
        rec = self._runs.get(str(run_id))
        if rec is not None:
            rec["finished"] = True
            if stats is not None:
                try:
                    rec["stats"] = dict(stats)
                except Exception:
                    rec["stats"] = stats

    # ---- Per-action annotations (in-memory) ----
    def save_run_action_annotation(
        self,
        *,
        run_id: str,
        action_index: int,
        label: str,
        source: str,
        notes: str | None = None,
        user_id: str | None = None,
        selector: dict | None = None,
        domain: str | None = None,
        tool: str | None = None,
        target_signature: dict | None = None,
    ) -> dict:
        import time as _time

        rid = str(run_id)
        idx = int(action_index)
        src = str(source)
        row = None
        for ann in self._annotations:
            if (
                ann.get("run_id") == rid
                and ann.get("action_index") == idx
                and ann.get("source") == src
            ):
                row = ann
                break
        if row is None:
            row = {
                "run_id": rid,
                "action_index": idx,
                "test_id": None,
                "step_id": None,
                "label": str(label),
                "source": src,
                "notes": notes,
                "user_id": user_id,
                "created_at": _time.time(),
                "selector": selector,
                "domain": domain,
                "tool": tool,
                "target_signature": target_signature,
            }
            self._annotations.append(row)
        else:
            row["label"] = str(label)
            row["notes"] = notes
            row["user_id"] = user_id
            row["created_at"] = _time.time()
            row["selector"] = selector if selector is not None else row.get("selector")
            row["domain"] = domain if domain is not None else row.get("domain")
            row["tool"] = tool if tool is not None else row.get("tool")
            row["target_signature"] = (
                target_signature if target_signature is not None else row.get("target_signature")
            )
        return dict(row)

    def get_run_action_annotations(self, run_id: str) -> list[dict]:
        rid = str(run_id)
        anns = [a for a in self._annotations if a.get("run_id") == rid]
        anns.sort(
            key=lambda a: (
                int(a.get("action_index", 0) or 0),
                float(a.get("created_at", 0.0) or 0.0),
            )
        )
        return [dict(a) for a in anns]

    def get_selector_feedback_for_test(self, test_id: str) -> dict:
        """In-memory stub: aggregate annotations by selector for a pseudo test_id.

        Since InMemoryStorage does not persist runs/tests, this groups on annotations
        whose test_id matches. Used only in dev/test environments.
        """
        fb: dict[str, dict[str, int]] = {}
        tid = str(test_id)
        for row in self._annotations:
            if str(row.get("test_id") or "") != tid:
                continue
            sel = row.get("selector") or {}
            if not isinstance(sel, dict):
                continue
            sel_type = sel.get("type")
            sel_value = sel.get("value")
            if not isinstance(sel_type, str) or not isinstance(sel_value, str):
                continue
            key = f"{sel_type}|{sel_value}"
            entry = fb.setdefault(key, {"passed": 0, "failed": 0, "total": 0})
            entry["total"] += 1
            lab = str(row.get("label") or "").lower()
            if lab == "passed":
                entry["passed"] += 1
            elif lab == "failed":
                entry["failed"] += 1
        return fb

    def get_preferred_selectors_for_test(self, test_id: str) -> dict[int, dict]:
        """In-memory equivalent of PostgresStorage.get_preferred_selectors_for_test.

        Returns a mapping of action_index -> {"type": ..., "value": ...} for
        selectors that have been explicitly marked as passed (and not dominated
        by failures) for the given test_id.
        """
        tid = str(test_id)
        # Aggregate per (action_index, selector)
        stats: dict[tuple[int, str, str], dict[str, int]] = {}
        sigs: dict[tuple[int, str, str], dict] = {}
        for row in self._annotations:
            if str(row.get("test_id") or "") != tid:
                continue
            try:
                idx = int(row.get("action_index", 0) or 0)
            except Exception:
                continue
            sel = row.get("selector") or {}
            if not isinstance(sel, dict):
                continue
            sel_type = sel.get("type")
            sel_value = sel.get("value")
            if not isinstance(sel_type, str) or not isinstance(sel_value, str):
                continue
            key = (idx, sel_type, sel_value)
            entry = stats.setdefault(key, {"passed": 0, "failed": 0})
            lab = str(row.get("label") or "").lower()
            if lab == "passed":
                entry["passed"] += 1
            elif lab == "failed":
                entry["failed"] += 1
            if key not in sigs:
                sig = row.get("target_signature")
                if isinstance(sig, dict):
                    sigs[key] = sig

        preferred: dict[int, dict] = {}
        for (idx, sel_type, sel_value), sf in stats.items():
            p = int(sf.get("passed", 0) or 0)
            f = int(sf.get("failed", 0) or 0)
            if p <= 0 or p < f:
                continue
            score = (p - f, p)
            existing = preferred.get(idx)
            if existing is not None:
                prev_p = int(existing.get("_passed", 0))
                prev_f = int(existing.get("_failed", 0))
                prev_score = (prev_p - prev_f, prev_p)
                if prev_score >= score:
                    continue
            sig = sigs.get((idx, sel_type, sel_value)) or {}
            attrs = sig.get("attrs") if isinstance(sig, dict) else None
            tag = sig.get("tag") if isinstance(sig, dict) else None
            preferred[idx] = {
                "type": sel_type,
                "value": sel_value,
                "attrs": attrs if isinstance(attrs, dict) else None,
                "tag": tag if isinstance(tag, str) else None,
                "_passed": p,
                "_failed": f,
            }

        # Strip internal counters
        for k, v in list(preferred.items()):
            if isinstance(v, dict):
                v.pop("_passed", None)
                v.pop("_failed", None)
                if "attrs" in v and not isinstance(v.get("attrs"), dict):
                    v.pop("attrs", None)
                if "tag" in v and not isinstance(v.get("tag"), str):
                    v.pop("tag", None)
        return preferred

    # ---- Minimal Locator Profiles (in-memory) ----
    def save_locator_profile(
        self, *, domain, tool: str, target_signature: dict, selector: dict
    ) -> None:
        import time as _time

        # normalize selector dict to minimal form
        sel_type = selector.get("type") if isinstance(selector, dict) else None
        sel_value = selector.get("value") if isinstance(selector, dict) else None
        if not isinstance(sel_type, str) or not isinstance(sel_value, str):
            return
        norm_sel = {"type": sel_type, "value": sel_value}
        now = _time.time()
        # dedupe by domain+tool+selector
        for row in self._profiles:
            if (
                row["tool"] == tool
                and row.get("domain") == domain
                and row["selector"] == norm_sel
            ):
                row["hits"] = int(row.get("hits", 0)) + 1
                row["last_seen"] = now
                return
        self._profiles.append(
            {
                "domain": domain,
                "tool": tool,
                "target_signature": dict(target_signature or {}),
                "selector": norm_sel,
                "hits": 1,
                "last_seen": now,
            }
        )

    def _sig_contains(self, sup: dict, sub: dict) -> bool:
        try:
            for k, v in (sub or {}).items():
                if k not in sup:
                    return False
                if sup[k] != v:
                    return False
            return True
        except Exception:
            return False

    def find_locator_profile(self, *, domain, tool: str, target_signature: dict):
        # Prefer domain match then global; prefer sig containment match; order by specificity then hits then last_seen
        matches = []
        for row in self._profiles:
            if row["tool"] != tool:
                continue
            dom_score = (
                1
                if (row.get("domain") and row.get("domain") == domain)
                else (0 if row.get("domain") is None else -1)
            )
            sig = row.get("target_signature") or {}
            if target_signature and self._sig_contains(sig, target_signature):
                # Prefer more specific stored signatures (row with more fields)
                try:
                    spec = len(sig)
                except Exception:
                    spec = 0
                matches.append(
                    (
                        2 + dom_score,
                        spec,
                        int(row.get("hits", 0)),
                        float(row.get("last_seen", 0.0)),
                        row,
                    )
                )
            elif not target_signature:
                # allow best-by-tool fallback
                matches.append(
                    (
                        dom_score,
                        0,
                        int(row.get("hits", 0)),
                        float(row.get("last_seen", 0.0)),
                        row,
                    )
                )
        if not matches:
            # try global if we didn't match a scoped domain
            for row in self._profiles:
                if row["tool"] != tool:
                    continue
                if target_signature and self._sig_contains(
                    row.get("target_signature") or {}, target_signature
                ):
                    matches.append(
                        (
                            0,
                            len(target_signature),
                            int(row.get("hits", 0)),
                            float(row.get("last_seen", 0.0)),
                            row,
                        )
                    )
                elif not target_signature:
                    matches.append(
                        (
                            0,
                            0,
                            int(row.get("hits", 0)),
                            float(row.get("last_seen", 0.0)),
                            row,
                        )
                    )
        if not matches:
            return None
        matches.sort(key=lambda t: (t[0], t[1], t[2], t[3]), reverse=True)
        row = matches[0][-1]
        return dict(row.get("selector") or {})


__all__ = ["InMemoryStorage"]
