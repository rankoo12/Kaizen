from fastapi import APIRouter, FastAPI, HTTPException
from typing import Any, Dict
from pydantic import TypeAdapter

from engine.core.types.dtos import TargetQuery, LocatorCandidates

router = APIRouter(prefix="/api")

# Adapters for runtime validation
TA_TargetQuery = TypeAdapter(TargetQuery)
TA_LocatorCandidates = TypeAdapter(LocatorCandidates)


def register_resolve_routes(app: FastAPI, resolver) -> None:
    @router.post("/resolve")
    async def resolve_endpoint(body: Dict[str, Any]):
        snapshot = body.get("snapshot")
        query_raw = body.get("query")
        if snapshot is None or query_raw is None:
            raise HTTPException(status_code=400, detail="Missing 'snapshot' or 'query'")

        # Validate 'query' against TypedDict
        try:
            query = TA_TargetQuery.validate_python(query_raw)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Invalid TargetQuery: {e!s}")

        # TODO: when PageSnapshot TypedDict exists, validate snapshot similarly
        try:
            result = resolver.resolve(query, snapshot)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"resolver error: {e!s}")

        if not result:
            raise HTTPException(status_code=404, detail="No candidates")

        # Validate response shape
        try:
            return TA_LocatorCandidates.validate_python(result)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Invalid LocatorCandidates from resolver: {e!s}",
            )

    app.include_router(router)
