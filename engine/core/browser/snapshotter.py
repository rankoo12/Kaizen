from .snapshot_dto import PageSnapshot


class Snapshotter:
    """Placeholder for DOM → PageSnapshot capture."""

    def capture(self) -> PageSnapshot:
        # temporary fake data
        return {
            "html_path": "mock.html",
            "candidates": [],
            "styles_index_path": None,
            "screenshot_path": None,
            "frames": [],
        }
