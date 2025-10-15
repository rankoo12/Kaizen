from typing import Literal, TypedDict, Optional, Dict, Any

ToolName = Literal[
    "open",
    "type",
    "click",
    "press",
    "waitFor",
    "assertVisible",
    "assertText",
    "assertUrl",
    "custom",
]


class ToolCall(TypedDict):
    """Single LLM-selected action with arguments (to be validated in Step 3)."""

    tool: ToolName
    args: Dict[str, Any]
    meta: Optional[Dict[str, Any]]
