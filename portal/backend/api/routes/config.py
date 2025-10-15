from fastapi import APIRouter

router = APIRouter(prefix="/config", tags=["config"])


@router.get("/models")
def models():
    return {
        "textLLMs": ["llama3:8b"],
        "visionLLMs": ["llava:7b"],
        "current": {"text": "llama3:8b"},
    }
