from engine.core.types.dtos import TargetQuery, LocatorCandidates
from engine.core.browser.snapshot_dto import PageSnapshot
from pydantic import TypeAdapter
from engine.core.config.container import Container  # use DI

TA_TargetQuery = TypeAdapter(TargetQuery)
TA_PageSnapshot = TypeAdapter(PageSnapshot)
TA_LocatorCandidates = TypeAdapter(LocatorCandidates)


def resolve_snapshot(snapshot: PageSnapshot, query: TargetQuery) -> LocatorCandidates:
    query = TA_TargetQuery.validate_python(query)
    snapshot = TA_PageSnapshot.validate_python(snapshot)

    resolver = Container().element_resolver()  # ← DI, no hardcoding
    result = resolver.resolve(query, snapshot)
    if not result:
        raise ValueError("No candidates found")

    return TA_LocatorCandidates.validate_python(result)
