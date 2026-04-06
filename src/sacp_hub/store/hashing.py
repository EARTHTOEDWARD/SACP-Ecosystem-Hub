from __future__ import annotations

import hashlib
import json
import math
from typing import Any


def _normalize_json(obj: Any) -> Any:
    if obj is None or isinstance(obj, (str, bool, int)):
        return obj
    if isinstance(obj, float):
        if not math.isfinite(obj):
            raise ValueError("Non-finite float values are not allowed for canonical hashing")
        if obj == 0.0:
            return 0.0
        return obj
    if isinstance(obj, list):
        return [_normalize_json(v) for v in obj]
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for key, value in obj.items():
            if not isinstance(key, str):
                raise TypeError("JSON object keys must be strings")
            out[key] = _normalize_json(value)
        return out
    raise TypeError(f"Unsupported type for canonical hashing: {type(obj).__name__}")


def canonical_json_bytes(obj: Any) -> bytes:
    normalized = _normalize_json(obj)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return f"sha256:{h.hexdigest()}"


def hash_json(obj: Any) -> str:
    return sha256_bytes(canonical_json_bytes(obj))
