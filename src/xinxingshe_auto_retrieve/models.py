"""Data models shared by the scraper, retriever and renderers."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Problem:
    """A problem as it appears in the source OJ homework/contest page."""

    pid: str
    title: str
    url: str
    statement: str = ""
    tid: str = ""
    label: str = ""  # 作业内相对编号，如 A/B/C
    error: str = ""


@dataclass
class Candidate:
    """One search hit returned by CPRet."""

    title: str
    source: str  # CPRet 的 OJ 名，如 Codeforces / Luogu / QOJ
    url: str
    score: float
    group: int = 0  # 该候选在搜索结果中的名次（用于关联重复题）
    is_duplicate: bool = False
    vjudge_oj: str | None = None
    vjudge_num: str | None = None

    @property
    def vjudge_token(self) -> str | None:
        """``[problem:OJ-题号]`` token understood by VJudge workbooks."""
        if self.vjudge_oj and self.vjudge_num:
            return f"[problem:{self.vjudge_oj}-{self.vjudge_num}]"
        return None

    def as_dict(self) -> dict:
        return {
            "title": self.title,
            "source": self.source,
            "url": self.url,
            "score": round(self.score, 4),
            "is_duplicate": self.is_duplicate,
            "vjudge_oj": self.vjudge_oj,
            "vjudge_num": self.vjudge_num,
            "vjudge_token": self.vjudge_token,
        }


@dataclass
class MatchResult:
    problem: Problem
    threshold: float
    candidates: list[Candidate] = field(default_factory=list)
    best: Candidate | None = None
    chosen: Candidate | None = None
    error: str = ""
    note: str = ""
    cached: bool = False

    @property
    def matched(self) -> bool:
        return bool(self.best and not self.error and self.best.score > self.threshold)

    @property
    def token(self) -> str | None:
        if not self.matched or not self.chosen:
            return None
        return self.chosen.vjudge_token

    def as_dict(self) -> dict:
        return {
            "pid": self.problem.pid,
            "label": self.problem.label,
            "title": self.problem.title,
            "url": self.problem.url,
            "matched": self.matched,
            "threshold": self.threshold,
            "score": round(self.best.score, 4) if self.best else None,
            "best": self.best.as_dict() if self.best else None,
            "chosen": self.chosen.as_dict() if self.chosen else None,
            "vjudge_token": self.token,
            "note": self.note,
            "error": self.error,
            "cached": self.cached,
            "candidates": [c.as_dict() for c in self.candidates],
        }
