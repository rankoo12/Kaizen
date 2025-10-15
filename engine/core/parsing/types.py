from typing import Protocol, List
from ..types.ontology import ToolCall


class IIntentParser(Protocol):
    """Free-text step → list of tool calls.

    SRP: No validation or execution here; only parsing.
    Returns: candidate ToolCalls (to be schema-validated in Step 3).
    """

    def parse(self, step_text: str) -> List[ToolCall]: ...
