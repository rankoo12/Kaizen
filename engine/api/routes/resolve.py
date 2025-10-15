from fastapi import APIRouter, FastAPI, HTTPException
from typing import Any, Dict
from pydantic import TypeAdapter
import fastjsonschema
import json
from pathlib import Path

from engine.core.types.dtos import TargetQuery, LocatorCandidates

router = APIRouter(prefix="/api")

# --- runtime validators ---
TA_TargetQuery = TypeAdapter(TargetQuery)
TA_LocatorCandidates = TypeAdapter(LocatorCandidates)

# --- load JSON Schema once at import ---
schema_path = (
    Path(__file__).resolve().parent.parent / "schemas" / "resolve_request.schema.json"
)
with open(schema_path, "r", encoding="utf-8") as f:
    _validate = fastjsonschema.compile(json.load(f))


def register_resolve_routes(app: FastAPI, resolver) -> None:
    @router.post("/resolve")
    async def resolve_endpoint(body: Dict[str, Any]):
        # --- 1. Schema validation (rejects malformed JSON immediately) ---
        try:
            _validate(body)
        except fastjsonschema.JsonSchemaException as e:
            raise HTTPException(
                status_code=422, detail=f"Schema validation failed: {e.message}"
            )

        # --- 2. TypedDict validation for query (extra safety) ---
        snapshot = body["snapshot"]
        query_raw = body["query"]
        try:
            query = TA_TargetQuery.validate_python(query_raw)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Invalid TargetQuery: {e!s}")

        # --- 3. Execute resolver ---
        try:
            result = resolver.resolve(query, snapshot)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"resolver error: {e!s}")

        if not result:
            raise HTTPException(status_code=404, detail="No candidates")

        # --- 4. Validate response shape ---
        try:
            return TA_LocatorCandidates.validate_python(result)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Invalid LocatorCandidates from resolver: {e!s}",
            )

    app.include_router(router)
