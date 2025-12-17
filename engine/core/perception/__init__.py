from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol

from typing_extensions import TypedDict


class ScreenshotDiff(TypedDict, total=False):
    """Simple numeric diff metrics for a pair of screenshots."""

    element_region_diff: float
    main_region_diff: float
    full_page_diff: float


class VisionFeatures(TypedDict, total=False):
    """Optional vision-derived hints (captions, coarse semantics).

    Filled only when a real vision adapter is wired in. For perception-core-v1
    this remains empty via NullVisionCaptioner.
    """

    element_caption: str
    page_caption: str
    before_after_caption: str
    looks_like_button: bool
    looks_like_input: bool
    looks_clickable: bool
    kind: str  # e.g. "icon", "card", "search_bar"


class PerceptionResult(TypedDict, total=False):
    """Per-action perception result attached to ActionRun.

    - screenshot_diff: numeric 3-layer diff metrics.
    - dom_snapshot_id: optional DOM snapshot reference (future use).
    - bbox: optional bounding box used for element crop.
    - vision: optional vision-derived hints (behind a feature flag).
    - has_before/has_after: whether underlying PNGs were present.
    - error: optional, for debug only; should not affect control flow.
    """

    screenshot_diff: ScreenshotDiff
    dom_snapshot_id: Optional[str]
    bbox: Optional[Dict[str, float]]
    vision: Optional[VisionFeatures]
    has_before: bool
    has_after: bool
    error: Optional[str]


class IPerceptionLayer(Protocol):
    """Core perception interface (always-on, deterministic).

    Implementations are expected to be:
      - deterministic (no randomness or external services),
      - bounded CPU cost,
      - safe to call on every action in CI.
    """

    def compute(
        self,
        *,
        tool: Optional[str],
        before_path: Optional[str],
        after_path: Optional[str],
        bbox: Optional[Dict[str, float]] = None,
        dom_snapshot_id: Optional[str] = None,
    ) -> PerceptionResult:
        ...


class IVisionCaptioner(Protocol):
    """Optional vision interface used only for feature generation.

    This is intentionally small and backend-agnostic so that a local VLM
    or captioning service can be wired in a later vision-assist-v1 phase
    without changing engine callers.
    """

    def describe(
        self,
        *,
        before_element_path: Optional[str],
        after_element_path: Optional[str],
        page_before_path: Optional[str],
        page_after_path: Optional[str],
        tool: Optional[str] = None,
    ) -> VisionFeatures:
        ...


class NullVisionCaptioner(IVisionCaptioner):
    """Default no-op vision adapter used in perception-core-v1.

    Returns an empty feature set so the PerceptionLayer can always depend on
    IVisionCaptioner without introducing non-determinism or heavy deps.
    """

    def describe(
        self,
        *,
        before_element_path: Optional[str],
        after_element_path: Optional[str],
        page_before_path: Optional[str],
        page_after_path: Optional[str],
        tool: Optional[str] = None,
    ) -> VisionFeatures:
        return VisionFeatures()


@dataclass
class PerceptionLayer(IPerceptionLayer):
    """Deterministic screenshot diff implementation (perception-core-v1).

    Responsibilities:
      - Load PNG screenshots when available.
      - Compute 3-layer diff metrics:
          * element_region_diff  (crop around bbox when provided),
          * main_region_diff     (coarse main-content or viewport region),
          * full_page_diff       (entire shared area).
      - Optionally call a vision captioner (null by default).
      - Emit basic OTel histograms when the SDK is available.
    """

    vision: IVisionCaptioner = NullVisionCaptioner()

    def compute(
        self,
        *,
        tool: Optional[str],
        before_path: Optional[str],
        after_path: Optional[str],
        bbox: Optional[Dict[str, float]] = None,
        dom_snapshot_id: Optional[str] = None,
    ) -> PerceptionResult:
        tool_name = str(tool or "").strip() or "<none>"

        # Load images best-effort; tolerate missing files.
        img_before, img_after, load_error = _load_image_pair(
            before_path, after_path
        )

        has_before = img_before is not None
        has_after = img_after is not None

        # When either side is missing, fall back to zeros.
        if img_before is None or img_after is None:
            result: PerceptionResult = {
                "screenshot_diff": ScreenshotDiff(
                    element_region_diff=0.0,
                    main_region_diff=0.0,
                    full_page_diff=0.0,
                ),
                "dom_snapshot_id": dom_snapshot_id,
                "bbox": bbox,
                "vision": None,
                "has_before": has_before,
                "has_after": has_after,
                "error": load_error,
            }
            _record_diff_metrics(tool_name, result["screenshot_diff"])
            return result

        # Normalize sizes (crop to shared region).
        img_before, img_after = _align_size(img_before, img_after)

        # Compute full-page diff first (baseline).
        full_diff = _diff_ratio(img_before, img_after)

        # Element-region diff: crop by bbox (with padding) when available;
        # otherwise fall back to full-page diff to keep semantics simple.
        element_diff = full_diff
        if bbox:
            crop_before, crop_after = _crop_bbox(img_before, img_after, bbox)
            if crop_before is not None and crop_after is not None:
                element_diff = _diff_ratio(crop_before, crop_after)

        # Main-content diff: when a bbox exists, expand it; otherwise use
        # a central viewport-like region (middle 60% height, 80% width).
        main_diff = full_diff
        crop_before_main, crop_after_main = _crop_main_region(
            img_before, img_after, bbox
        )
        if crop_before_main is not None and crop_after_main is not None:
            main_diff = _diff_ratio(crop_before_main, crop_after_main)

        diffs: ScreenshotDiff = ScreenshotDiff(
            element_region_diff=float(element_diff),
            main_region_diff=float(main_diff),
            full_page_diff=float(full_diff),
        )

        # Default vision is null; real adapters can be wired later.
        vision_features: Optional[VisionFeatures] = None
        try:
            if self.vision is not None:
                vision_features = self.vision.describe(
                    before_element_path=None,
                    after_element_path=None,
                    page_before_path=before_path,
                    page_after_path=after_path,
                    tool=tool,
                )
        except Exception:
            vision_features = None

        result = PerceptionResult(
            screenshot_diff=diffs,
            dom_snapshot_id=dom_snapshot_id,
            bbox=bbox,
            vision=vision_features,
            has_before=has_before,
            has_after=has_after,
            error=load_error,
        )

        _record_diff_metrics(tool_name, diffs)
        return result


# --------- internal helpers (pure functions; easy to unit test) ---------


def _load_image_pair(
    before_path: Optional[str],
    after_path: Optional[str],
):
    """Load PNGs best-effort; return (before, after, error_message)."""

    try:
        from PIL import Image  # type: ignore
    except Exception:
        # Pillow not available – degrade to zeros but surface a hint.
        return None, None, "pillow_not_available"

    error: Optional[str] = None
    img_before = None
    img_after = None
    try:
        if before_path:
            img_before = Image.open(before_path).convert("RGBA")
    except Exception:
        error = "before_load_error"
        img_before = None
    try:
        if after_path:
            img_after = Image.open(after_path).convert("RGBA")
    except Exception:
        # Do not overwrite an earlier error; append instead.
        error = (error + "+after_load_error") if error else "after_load_error"
        img_after = None
    return img_before, img_after, error


def _align_size(img_before, img_after):
    """Crop both images to the shared top-left region to ensure equal size."""

    w = min(int(img_before.width), int(img_after.width))
    h = min(int(img_before.height), int(img_after.height))
    if w <= 0 or h <= 0:
        return img_before, img_after
    box = (0, 0, w, h)
    try:
        img_before_c = img_before.crop(box)
    except Exception:
        img_before_c = img_before
    try:
        img_after_c = img_after.crop(box)
    except Exception:
        img_after_c = img_after
    return img_before_c, img_after_c


def _diff_ratio(img_before, img_after) -> float:
    """Return a simple [0,1] diff ratio based on changed area.

    Uses ImageChops.difference and the bounding box of non-zero pixels; the
    ratio is (changed_area / total_area). This is deterministic and cheap,
    and correlates well with "how much visually changed" for QA purposes.
    """

    try:
        from PIL import ImageChops  # type: ignore
    except Exception:
        return 0.0

    try:
        diff = ImageChops.difference(img_before, img_after)
        bbox = diff.getbbox()
        if not bbox:
            return 0.0
        x0, y0, x1, y1 = bbox
        changed_area = max(0, int(x1 - x0)) * max(0, int(y1 - y0))
        total_area = max(1, int(img_before.width) * int(img_before.height))
        return max(0.0, min(1.0, changed_area / float(total_area)))
    except Exception:
        return 0.0


def _crop_bbox(img_before, img_after, bbox: Dict[str, float]):
    """Crop element region with small padding based on bbox.

    Bbox keys are expected to be x, y, width, height in page coordinates.
    """

    try:
        x = float(bbox.get("x", 0.0))
        y = float(bbox.get("y", 0.0))
        w = float(bbox.get("width", 0.0))
        h = float(bbox.get("height", 0.0))
    except Exception:
        return None, None

    if w <= 0 or h <= 0:
        return None, None

    pad = 4.0
    x0 = max(0, int(x - pad))
    y0 = max(0, int(y - pad))
    x1 = min(int(img_before.width), int(x + w + pad))
    y1 = min(int(img_before.height), int(y + h + pad))
    if x1 <= x0 or y1 <= y0:
        return None, None
    box = (x0, y0, x1, y1)
    try:
        before_crop = img_before.crop(box)
        after_crop = img_after.crop(box)
        return before_crop, after_crop
    except Exception:
        return None, None


def _crop_main_region(img_before, img_after, bbox: Optional[Dict[str, float]]):
    """Return a coarse 'main content' crop for diffing.

    If a bbox is provided, expand it; otherwise use a central viewport-like
    region (80% width, 60% height).
    """

    w = int(img_before.width)
    h = int(img_before.height)
    if w <= 0 or h <= 0:
        return None, None

    if bbox:
        try:
            x = float(bbox.get("x", 0.0))
            y = float(bbox.get("y", 0.0))
            bw = float(bbox.get("width", 0.0))
            bh = float(bbox.get("height", 0.0))
        except Exception:
            x = y = 0.0
            bw = float(w)
            bh = float(h)
        # Expand bbox by a factor but stay within image bounds.
        scale = 2.5
        cx = x + bw / 2.0
        cy = y + bh / 2.0
        hw = (bw * scale) / 2.0
        hh = (bh * scale) / 2.0
        x0 = max(0, int(cx - hw))
        y0 = max(0, int(cy - hh))
        x1 = min(w, int(cx + hw))
        y1 = min(h, int(cy + hh))
    else:
        # Fallback: central viewport-ish region
        vw = int(w * 0.8)
        vh = int(h * 0.6)
        x0 = max(0, int((w - vw) / 2))
        y0 = max(0, int((h - vh) / 2))
        x1 = min(w, x0 + vw)
        y1 = min(h, y0 + vh)

    if x1 <= x0 or y1 <= y0:
        return None, None

    box = (x0, y0, x1, y1)
    try:
        return img_before.crop(box), img_after.crop(box)
    except Exception:
        return None, None


# --------- metrics (OTel histograms, bounded cardinality) ---------

_OTEL_READY = False
_OTEL_HIST_ELEMENT = None
_OTEL_HIST_MAIN = None
_OTEL_HIST_FULL = None


def _ensure_otel_meter() -> None:
    global _OTEL_READY, _OTEL_HIST_ELEMENT, _OTEL_HIST_MAIN, _OTEL_HIST_FULL
    if _OTEL_READY:
        return
    try:
        from opentelemetry import metrics as _otel_metrics  # type: ignore
    except Exception:
        _OTEL_READY = False
        return
    try:
        meter = _otel_metrics.get_meter("kaizen.engine.perception")
        _OTEL_HIST_ELEMENT = meter.create_histogram(
            name="kaizen_perception_element_diff_ratio",
            unit="1",
            description="Perception diff ratio at element region",
        )
        _OTEL_HIST_MAIN = meter.create_histogram(
            name="kaizen_perception_main_diff_ratio",
            unit="1",
            description="Perception diff ratio at main-content region",
        )
        _OTEL_HIST_FULL = meter.create_histogram(
            name="kaizen_perception_full_diff_ratio",
            unit="1",
            description="Perception diff ratio at full page",
        )
        _OTEL_READY = True
    except Exception:
        _OTEL_READY = False
        _OTEL_HIST_ELEMENT = None
        _OTEL_HIST_MAIN = None
        _OTEL_HIST_FULL = None


def _record_diff_metrics(tool: str, diffs: ScreenshotDiff) -> None:
    """Record histogram samples when OTel SDK is available.

    Cardinality is bounded by the small set of tool names plus the fixed
    {element, main, full} region labels.
    """

    if not diffs:
        return
    _ensure_otel_meter()
    if not _OTEL_READY:
        return
    attrs = {"tool": str(tool or "<none>")}
    try:
        if _OTEL_HIST_ELEMENT is not None and "element_region_diff" in diffs:
            _OTEL_HIST_ELEMENT.record(float(diffs["element_region_diff"]), attributes=attrs)
    except Exception:
        pass
    try:
        if _OTEL_HIST_MAIN is not None and "main_region_diff" in diffs:
            _OTEL_HIST_MAIN.record(float(diffs["main_region_diff"]), attributes=attrs)
    except Exception:
        pass
    try:
        if _OTEL_HIST_FULL is not None and "full_page_diff" in diffs:
            _OTEL_HIST_FULL.record(float(diffs["full_page_diff"]), attributes=attrs)
    except Exception:
        pass


__all__ = [
    "ScreenshotDiff",
    "VisionFeatures",
    "PerceptionResult",
    "IPerceptionLayer",
    "IVisionCaptioner",
    "NullVisionCaptioner",
    "PerceptionLayer",
]
