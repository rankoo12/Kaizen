from __future__ import annotations

from typing import Dict, Iterable, List
import math
import re


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


def embed_signature(sig: Dict, dim: int = 64) -> List[float]:
    """Deterministic hashing embedder for target signatures.

    Produces a fixed-size vector using a bag‑of‑words hashing trick. Not a
    semantic model; serves as a pgvector‑ready placeholder with stable behavior.
    """
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


def cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return float(sum(x * y for x, y in zip(a, b)))
