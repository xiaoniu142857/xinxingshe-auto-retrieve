"""JSON cache for CPRet search results (keyed by the query text)."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from pathlib import Path

from .models import Candidate

CACHE_VERSION = 1


class ResultCache:
    """Disk cache for ``CPRetClient.search`` results.

    A cached entry is reused when it is younger than ``ttl_days``; ``ttl_days=0``
    disables the cache entirely (used by ``--refresh`` / ``--no-result-cache``).
    Entries are written atomically so parallel workers cannot corrupt each other.
    """

    def __init__(
        self,
        directory: Path,
        ttl_days: float,
        api_url: str,
        bypass_read: bool = False,
    ) -> None:
        self.directory = Path(directory)
        self.ttl_seconds = max(0.0, float(ttl_days)) * 86400.0
        self.api_url = api_url
        self.enabled = self.ttl_seconds > 0
        # --refresh 时跳过旧结果，但仍然写入新结果供下次使用。
        self.bypass_read = bypass_read

    def _path(self, query: str) -> Path:
        digest = hashlib.sha256(
            f"{CACHE_VERSION}\x00{self.api_url}\x00{query}".encode("utf-8")
        ).hexdigest()
        return self.directory / f"{digest}.json"

    def load(self, query: str) -> tuple[list[Candidate], int, float] | None:
        if not self.enabled or self.bypass_read:
            return None
        path = self._path(query)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if data.get("version") != CACHE_VERSION:
            return None
        created_at = float(data.get("created_at") or 0.0)
        if time.time() - created_at > self.ttl_seconds:
            return None

        candidates: list[Candidate] = []
        for item in data.get("candidates") or []:
            candidates.append(
                Candidate(
                    title=str(item.get("title") or ""),
                    source=str(item.get("source") or ""),
                    url=str(item.get("url") or ""),
                    score=float(item.get("score") or 0.0),
                    group=int(item.get("group") or 0),
                    is_duplicate=bool(item.get("is_duplicate")),
                )
            )
        return candidates, int(data.get("total") or 0), float(data.get("elapsed") or 0.0)

    def store(
        self, query: str, candidates: list[Candidate], total: int, elapsed: float
    ) -> None:
        if not self.enabled or not candidates:
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": CACHE_VERSION,
            "created_at": time.time(),
            "api": self.api_url,
            "total": total,
            "elapsed": elapsed,
            "candidates": [
                {
                    "title": c.title,
                    "source": c.source,
                    "url": c.url,
                    "score": c.score,
                    "group": c.group,
                    "is_duplicate": c.is_duplicate,
                }
                for c in candidates
            ],
        }
        path = self._path(query)
        # 同名查询可能被多个线程同时写入，用唯一临时名避免互相覆盖。
        tmp = path.with_name(f"{path.name}.{secrets.token_hex(4)}.tmp")
        try:
            tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, path)
        except OSError:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
