from __future__ import annotations

from typing import Dict, Iterable, List
import math
import re
import json
from functools import lru_cache

from engine.core.config.settings import settings as _settings


_WORD_RX = re.compile(r"[A-Za-z0-9_]+")


def _tokens_from_signature(sig: Dict) -> Iterable[str]:
    if not isinstance(sig, dict):
        return []
    toks: List[str] = []
    for k, v in sig.items():
        try:
            key = str(k).lower().strip()
        except Exception:
            key = ""
        if not key:
            continue
        toks.append(f"k:{key}")
        if isinstance(v, str):
            for m in _WORD_RX.findall(v.lower()):
                toks.append(f"t:{m}")
        elif isinstance(v, (int, float)):
            toks.append(f"n:{v}")
        elif isinstance(v, dict):
            # shallow nest: include known stable attributes
            for nk in ("id", "testid", "name", "role", "type", "text"):
                nv = v.get(nk)
                if isinstance(nv, str):
                    for m in _WORD_RX.findall(nv.lower()):
                        toks.append(f"t:{m}")
        elif isinstance(v, list):
            for it in v:
                if isinstance(it, str):
                    for m in _WORD_RX.findall(it.lower()):
                        toks.append(f"t:{m}")
    return toks


def _hash_embed(sig: Dict, dim: int) -> List[float]:
    dim = int(dim or 64)
    vec = [0.0] * dim
    for tok in _tokens_from_signature(sig):
        try:
            idx = hash(tok) % dim
        except Exception:
            continue
        vec[idx] += 1.0
    # L2 normalize
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0:
        vec = [x / norm for x in vec]
    return vec


@lru_cache(maxsize=1)
def _get_sbert_model():
    """Lazily construct SBERT model when enabled.

    If sentence-transformers is unavailable, returns None and callers
    fall back to hash-based embeddings.
    """
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
    except Exception:
        return None
    model_name = getattr(_settings, "RETRIEVAL_SBERT_MODEL", "all-MiniLM-L6-v2")
    try:
        return SentenceTransformer(model_name)
    except Exception:
        return None


def _sbert_embed(sig: Dict, dim: int) -> List[float]:
    model = _get_sbert_model()
    if model is None:
        return _hash_embed(sig, dim)
    toks = list(_tokens_from_signature(sig))
    text = " ".join(toks) if toks else json.dumps(sig, sort_keys=True)
    vec = model.encode([text], normalize_embeddings=True)[0]
    if len(vec) == dim:
        return [float(x) for x in vec]
    out = [0.0] * dim
    for i in range(min(dim, len(vec))):
        out[i] = float(vec[i])
    norm = math.sqrt(sum(x * x for x in out))
    if norm > 0:
        out = [x / norm for x in out]
    return out


_EMBED_CACHE: dict[str, List[float]] = {}


def embed_signature(sig: Dict, dim: int = 64) -> List[float]:
    """Embed target signatures using configured backend.

    Default is deterministic hash-based embedding. When
    RETRIEVAL_EMBED_MODE is "sbert" and sentence-transformers is
    available, a small SBERT model is used instead. Results are cached
    with a bounded in-memory cache.
    """
    try:
        eff_dim = int(dim or getattr(_settings, "RETRIEVAL_EMBED_DIM", 64) or 64)
    except Exception:
        eff_dim = int(dim or 64)
    key = json.dumps(sig or {}, sort_keys=True)
    if key in _EMBED_CACHE:
        return _EMBED_CACHE[key]
    mode = str(getattr(_settings, "RETRIEVAL_EMBED_MODE", "hash") or "hash").lower()
    if mode == "sbert":
        vec = _sbert_embed(sig, eff_dim)
    else:
        vec = _hash_embed(sig, eff_dim)
    try:
        max_entries = int(getattr(_settings, "RETRIEVAL_EMBED_CACHE_MAX", 1024) or 1024)
    except Exception:
        max_entries = 1024
    if max_entries > 0:
        if len(_EMBED_CACHE) >= max_entries:
            try:
                _EMBED_CACHE.pop(next(iter(_EMBED_CACHE)))
            except Exception:
                _EMBED_CACHE.clear()
        _EMBED_CACHE[key] = vec
    return vec


def cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return float(sum(x * y for x, y in zip(a, b)))
