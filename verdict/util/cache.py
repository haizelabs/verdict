import hashlib
import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


def _json_dumps_stable(obj: Any) -> str:
    """Stable JSON dump that handles non-serializable objects by stringifying.

    This is used to generate cache keys and payloads deterministically.
    """

    def default(o):
        try:
            return dict(o)
        except Exception:
            return str(o)

    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=default)


def make_hash_key(obj: Any) -> str:
    data = _json_dumps_stable(obj).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


@dataclass
class CachePayload:
    """Represents a cached unit result.

    Fields:
      - response: dict (Schema.model_dump())
      - usage: dict with in_tokens, out_tokens (optional)
      - meta: dict with model, extractor, unit, etc.
    """

    response: dict
    usage: dict | None
    meta: dict


class Cache:
    def get(self, key: str) -> Optional[CachePayload]:  # pragma: no cover - interface
        raise NotImplementedError

    def set(self, key: str, payload: CachePayload) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class DirectoryCache(Cache):
    """A simple content-addressed cache using files under a directory.

    Each entry is stored as one JSON file named {key}.json. Thread-safe via a
    process-local lock; external concurrent processes are not guarded.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def get(self, key: str) -> Optional[CachePayload]:
        path = self._path(key)
        with self._lock:
            if not path.exists():
                return None
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return CachePayload(
                    response=data.get("response", {}),
                    usage=data.get("usage"),
                    meta=data.get("meta", {}),
                )
            except Exception:
                # Corrupt cache entry; ignore
                return None

    def set(self, key: str, payload: CachePayload) -> None:
        path = self._path(key)
        data = {
            "response": payload.response,
            "usage": payload.usage,
            "meta": payload.meta,
        }
        content = _json_dumps_stable(data)
        with self._lock:
            path.write_text(content, encoding="utf-8")


def build_unit_cache_key(
    *,
    unit_prefix: list[str] | None,
    messages: list[dict],
    model_name: str,
    extractor: str,
    response_schema: str,
) -> str:
    """Deterministically build a cache key for a unit execution.

    We intentionally omit any nonce and streaming variations from the messages.
    """
    key_obj = {
        "unit": unit_prefix or [],
        "messages": messages,
        "model": model_name,
        "extractor": extractor,
        "response_schema": response_schema,
    }
    return make_hash_key(key_obj)

