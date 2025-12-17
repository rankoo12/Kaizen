from pathlib import Path

from engine.core.perception import PerceptionLayer


def _make_png(path: Path, *, color: tuple[int, int, int, int] = (255, 255, 255, 255)) -> None:
    from PIL import Image  # type: ignore

    img = Image.new("RGBA", (50, 50), color)
    img.save(path)


def _make_png_with_rect(
    path: Path,
    *,
    bg: tuple[int, int, int, int] = (255, 255, 255, 255),
    rect: tuple[int, int, int, int] = (10, 10, 20, 20),
    rect_color: tuple[int, int, int, int] = (0, 0, 0, 255),
) -> None:
    from PIL import Image, ImageDraw  # type: ignore

    img = Image.new("RGBA", (50, 50), bg)
    draw = ImageDraw.Draw(img)
    x0, y0, x1, y1 = rect
    draw.rectangle([x0, y0, x1, y1], fill=rect_color)
    img.save(path)


def test_perception_zero_diff_for_identical_images(tmp_path):
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    _make_png(before)
    _make_png(after)

    layer = PerceptionLayer()
    res = layer.compute(
        tool="click",
        before_path=str(before),
        after_path=str(after),
        bbox=None,
        dom_snapshot_id=None,
    )

    diffs = res["screenshot_diff"]
    assert diffs["element_region_diff"] == 0.0
    assert diffs["main_region_diff"] == 0.0
    assert diffs["full_page_diff"] == 0.0
    assert res["has_before"] is True
    assert res["has_after"] is True


def test_perception_element_diff_at_least_full_diff_when_bbox_changes(tmp_path):
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    _make_png(before)
    # Draw a small changed rectangle inside the bbox region
    _make_png_with_rect(after, rect=(15, 15, 30, 30))

    layer = PerceptionLayer()
    bbox = {"x": 14.0, "y": 14.0, "width": 20.0, "height": 20.0}
    res = layer.compute(
        tool="click",
        before_path=str(before),
        after_path=str(after),
        bbox=bbox,
        dom_snapshot_id="dom_snap_test",
    )

    diffs = res["screenshot_diff"]
    # All diffs should be bounded in [0, 1]. When the full-page diff
    # is non-zero, element/main diffs should not be smaller than it.
    assert 0.0 <= diffs["full_page_diff"] <= 1.0
    assert 0.0 <= diffs["element_region_diff"] <= 1.0
    assert 0.0 <= diffs["main_region_diff"] <= 1.0
    if diffs["full_page_diff"] > 0.0:
        assert diffs["element_region_diff"] >= diffs["full_page_diff"]
        assert diffs["main_region_diff"] >= diffs["full_page_diff"]
    assert res["dom_snapshot_id"] == "dom_snap_test"
    assert res["has_before"] is True
    assert res["has_after"] is True
    # Vision is effectively empty by default in perception-core-v1
    assert not res.get("vision")
