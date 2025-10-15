from typing import List, Optional, Literal, Dict, Any
from typing_extensions import TypedDict


class StepSpec(TypedDict, total=False):
    index: int
    text: str
    timeout: Optional[int]
    data: Optional[Dict[str, Any]]


class TestSpec(TypedDict, total=False):
    id: str
    name: str
    steps: List[StepSpec]
    vars: Dict[str, Any]
    tags: List[str]


class TargetHints(TypedDict, total=False):
    role: Optional[str]
    color: Optional[str]
    near: Optional[str]


class TargetQuery(TypedDict, total=False):
    text: str
    hints: TargetHints
    scope: Optional[str]


class Locator(TypedDict, total=False):
    type: Literal["role", "css", "xpath", "id", "testid"]
    value: str
    framePath: Optional[List[int]]
    shadowPath: Optional[List[int]]


class LocatorCandidates(TypedDict, total=False):
    primary: Locator
    fallbacks: List[Locator]
    confidence: float
    reason: str
    bbox: Optional[Dict[str, float]]
