from typing import List, Optional, Dict, Any
from typing_extensions import TypedDict


class Candidate(TypedDict, total=False):
    tag: str
    id: str
    classes: List[str]
    role: Optional[str]
    text: Optional[str]
    aria_label: Optional[str]
    visible: bool
    clickable: bool
    bbox: Dict[str, float]  # x, y, width, height
    color: Optional[str]


class FrameSnapshot(TypedDict, total=False):
    frame_id: str
    html_path: str
    candidates: List[Candidate]


class PageSnapshot(TypedDict, total=False):
    """Serializable structure for a captured page DOM."""

    html_path: str
    candidates: List[Candidate]
    styles_index_path: Optional[str]
    screenshot_path: Optional[str]
    frames: List[FrameSnapshot]
