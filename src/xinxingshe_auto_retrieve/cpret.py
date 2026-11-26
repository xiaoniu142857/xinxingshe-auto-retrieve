"""CPRet (https://cpret.online) retrieval client.

CPRet exposes ``POST /api/search``.  The JSON response contains rendered result
cards under ``html``; we parse those cards instead of relying on an unstable
private JSON schema.
"""

from __future__ import annotations

import threading
import time

import requests
from bs4 import BeautifulSoup

from .models import Candidate

DEFAULT_API = "https://cpret.online/api/search"


class CPRetError(RuntimeError):
    pass


def parse_results(html: str) -> list[Candidate]:
    """Parse CPRet result-card HTML into candidates (including folded duplicates)."""
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[Candidate] = []

    for group, li in enumerate(soup.select("li.result-card")):
        classes = li.get("class") or []
        if "sample-card" in classes:
            continue
        title_node = li.select_one("a.result-title")
        if title_node is None:
            continue
        score_node = li.select_one(".score-num")
        source_node = li.select_one(".oj-tag")
        try:
            score = float(score_node.get_text(strip=True)) if score_node else 0.0
        except ValueError:
            score = 0.0
        candidates.append(
            Candidate(
                title=title_node.get_text(" ", strip=True),
                source=source_node.get_text(strip=True) if source_node else "",
                url=title_node.get("href") or "",
                score=score,
                group=group,
            )
        )

        for dup in li.select("details.dups li"):
            dup_title = dup.select_one("a.t") or dup.select_one("a.result-title")
            if dup_title is None:
                continue
            dup_score_node = dup.select_one(".num")
            try:
                dup_score = float(dup_score_node.get_text(strip=True)) if dup_score_node else 0.0
            except ValueError:
                dup_score = 0.0
            if not dup_score:
                dup_score = score
            dup_source = dup.select_one(".oj-tag")
            candidates.append(
                Candidate(
                    title=dup_title.get_text(" ", strip=True),
                    source=dup_source.get_text(strip=True) if dup_source else "",
                    url=dup_title.get("href") or "",
                    score=dup_score,
                    group=group,
                    is_duplicate=True,
                )
            )
    return candidates


class CPRetClient:
    def __init__(
        self,
        api_url: str = DEFAULT_API,
        timeout: float = 180.0,
        retries: int = 3,
        max_query_chars: int = 8000,
    ) -> None:
        self.api_url = api_url
        self.timeout = timeout
        self.retries = retries
        self.max_query_chars = max_query_chars
        self._headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/143.0 Safari/537.36"
            ),
            "Accept": "application/json",
            "Origin": "https://cpret.online",
            "Referer": "https://cpret.online/",
        }
        # requests.Session 不是线程安全的；每个查询线程用独立连接池。
        self._local = threading.local()

    def _session(self) -> requests.Session:
        session = getattr(self._local, "session", None)
        if session is None:
            session = requests.Session()
            session.headers.update(self._headers)
            self._local.session = session
        return session

    def search(self, query: str) -> tuple[list[Candidate], int, float]:
        """Return ``(candidates, total_results, elapsed_ms)`` for a statement."""
        query = query.strip()
        if not query:
            raise CPRetError("查询文本为空。")
        if len(query) > self.max_query_chars:
            query = query[: self.max_query_chars]

        payload = {
            "q": query,
            "page": 1,
            "count": False,
            "dedup": True,
            "mmr": False,
            "mode": "text",
        }

        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                response = self._session().post(
                    self.api_url, json=payload, timeout=self.timeout
                )
            except requests.RequestException as exc:
                last_error = exc
                if attempt + 1 < self.retries:
                    time.sleep(2.0 * (attempt + 1))
                    continue
                raise CPRetError(f"CPRet 请求失败：{exc}") from exc

            if response.status_code == 200:
                break
            if response.status_code in (429, 500, 502, 503, 504) and attempt + 1 < self.retries:
                time.sleep(2.0 * (attempt + 1))
                last_error = CPRetError(f"CPRet 返回 HTTP {response.status_code}")
                continue
            detail = response.text[:200].replace("\n", " ")
            raise CPRetError(f"CPRet 返回 HTTP {response.status_code}：{detail}")
        else:
            raise CPRetError(f"CPRet 多次重试仍失败：{last_error}")

        try:
            data = response.json()
        except ValueError as exc:
            raise CPRetError("CPRet 返回的不是合法 JSON。") from exc

        if "error" in data:
            raise CPRetError(f"CPRet 错误：{data['error']}")
        html = data.get("html") or ""
        total = int(data.get("total") or 0)
        elapsed = float(data.get("elapsed") or 0.0)
        return parse_results(html), total, elapsed
