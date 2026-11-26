"""End-to-end pipeline: Hydro homework -> CPRet -> VJudge workbook.

Performance notes:
- homework statements are fetched with a small thread pool;
- CPRet queries run concurrently with a shared rate limiter;
- statements and CPRet results are cached on disk, so a second run is nearly
  instant unless ``--refresh`` is used.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from functools import partial
from pathlib import Path

from .cache import ResultCache
from .cpret import CPRetClient, CPRetError
from .hydro import HydroClient, HydroError, Target, parse_target
from .models import Candidate, MatchResult, Problem
from .render import render_console, render_report, render_workbook
from .vjudge import apply_mapping

CPRET_API = "https://cpret.online/api/search"


class PipelineError(RuntimeError):
    pass


class _RateLimiter:
    """Reserve request start slots so concurrent queries stay spaced out."""

    def __init__(self, interval: float) -> None:
        self.interval = max(0.0, float(interval))
        self._lock = threading.Lock()
        self._next_start = 0.0

    def wait(self) -> None:
        if self.interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            start = max(now, self._next_start)
            self._next_start = start + self.interval
        delay = start - time.monotonic()
        if delay > 0:
            time.sleep(delay)


@dataclass
class Config:
    url: str
    user: str
    password: str
    threshold: float = 0.7
    out_dir: Path = Path("output")
    cache_dir: Path = Path(".cache")
    delay: float = 0.4
    timeout: float = 30.0
    cpret_timeout: float = 180.0
    max_query_chars: int = 8000
    top: int = 3
    refresh: bool = False
    only: list[str] = field(default_factory=list)
    dry_run: bool = False
    quiet: bool = False
    include_missing: bool = True
    compact_workbook: bool = True
    max_problems: int | None = None
    fetch_workers: int = 6
    query_workers: int = 3
    result_cache: bool = True
    cache_ttl_days: float = 14.0
    timings: bool = False


@dataclass
class Outcome:
    target: Target
    config: Config
    problems: list[Problem]
    results: list[MatchResult]
    files: dict[str, Path] = field(default_factory=dict)
    timings: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "source_url": self.target.page_url,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "threshold": self.config.threshold,
            "timings": {k: round(v, 3) for k, v in self.timings.items()},
            "problems": [r.as_dict() for r in self.results],
        }


def _matches_only(problem: Problem, needles: list[str]) -> bool:
    if not needles:
        return True
    haystack = f"{problem.pid} {problem.label} {problem.title}".lower()
    return any(needle.lower() in haystack for needle in needles)


def _load_cache_data(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return list(data.get("problems") or [])


def _load_cache(path: Path) -> dict[str, str]:
    return {
        p["pid"]: p.get("statement", "")
        for p in _load_cache_data(path)
        if p.get("pid")
    }


def _save_cache(path: Path, problems: list[Problem], previous: dict[str, str]) -> None:
    """Merge current problems into the cache.

    只处理了部分题（``--only`` / ``--max-problems``）时，不能把整个缓存文件
    覆盖成子集；已缓存的其它题面要原样保留。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    entries = {p["pid"]: p for p in _load_cache_data(path) if p.get("pid")}
    for p in problems:
        old = entries.get(p.pid) or {}
        entries[p.pid] = {
            "pid": p.pid,
            "title": p.title,
            "url": p.url,
            "tid": p.tid,
            "label": p.label,
            "statement": p.statement or previous.get(p.pid) or old.get("statement", ""),
        }
    path.write_text(
        json.dumps({"problems": list(entries.values())}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _choose(best: Candidate | None, candidates: list[Candidate]) -> tuple[Candidate | None, str]:
    """Pick the candidate used for the VJudge token."""
    if best is None:
        return None, ""
    if best.vjudge_token:
        return best, ""
    same_group = [
        c
        for c in candidates
        if c.group == best.group and c.is_duplicate and c.vjudge_token
    ]
    if same_group:
        pick = max(same_group, key=lambda c: c.score)
        return pick, f"最高分题目在 VJudge 不可直接使用，采用同题版本：{pick.source}"
    return best, "已找到原题，但无法生成 VJudge 题号"


def _log(config: Config, message: str, *, newline: bool = False) -> None:
    if config.quiet:
        return
    print(message, end="\n" if newline else "", file=sys.stderr, flush=True)


def _fetch_one(client: HydroClient, problem: Problem) -> tuple[Problem, str, str]:
    try:
        return problem, client.fetch_statement(problem), ""
    except Exception as exc:  # 单题失败不应中断整批
        return problem, "", f"{type(exc).__name__}: {exc}"


def run(config: Config) -> Outcome:
    t_start = time.perf_counter()
    target = parse_target(config.url)
    client = HydroClient(
        target,
        user=config.user,
        password=config.password,
        timeout=config.timeout,
    )
    client.login()
    problems = client.fetch_problems()

    if config.only:
        problems = [p for p in problems if _matches_only(p, config.only)]
        if not problems:
            raise PipelineError(f"--only {config.only} 没有匹配到任何题目。")
    if config.max_problems:
        problems = problems[: config.max_problems]

    if config.dry_run:
        return Outcome(target=target, config=config, problems=problems, results=[])

    t_after_list = time.perf_counter()

    cache_path = config.cache_dir / f"{target.domain}-{target.tid}.json"
    cached = {} if config.refresh else _load_cache(cache_path)

    pending = [p for p in problems if config.refresh or not cached.get(p.pid)]
    if pending:
        workers = max(1, min(config.fetch_workers, len(pending)))
        _log(config, f"抓取题面：{len(pending)} 题（并发 {workers}）...", newline=True)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for problem, statement, error in pool.map(
                partial(_fetch_one, client), pending
            ):
                if statement:
                    problem.statement = statement
                    problem.error = ""
                elif cached.get(problem.pid):
                    # 刷新失败时退回旧缓存，不把一次网络抖动当成整题失败。
                    problem.statement = cached[problem.pid]
                else:
                    problem.error = error or "题面抓取失败"
    for problem in problems:
        if not problem.statement and not problem.error:
            problem.statement = cached.get(problem.pid, "")
    _save_cache(cache_path, problems, cached)

    t_after_fetch = time.perf_counter()

    cpret = CPRetClient(
        api_url=CPRET_API,
        timeout=config.cpret_timeout,
        max_query_chars=config.max_query_chars,
    )
    result_cache = ResultCache(
        config.cache_dir / "cpret",
        0.0 if not config.result_cache else config.cache_ttl_days,
        f"{CPRET_API}#maxchars={config.max_query_chars}",
        bypass_read=config.refresh,
    )
    limiter = _RateLimiter(config.delay)

    def process(problem: Problem) -> MatchResult:
        result = MatchResult(problem=problem, threshold=config.threshold)
        if problem.error:
            result.error = problem.error
            return result

        statement = problem.statement.strip()
        if not statement:
            result.error = "题面为空"
            return result
        query = f"{problem.title}\n{statement}" if problem.title else statement
        truncated = len(query) > config.max_query_chars

        hit = result_cache.load(query)
        if hit is not None:
            candidates, total, elapsed = hit
            result.cached = True
        else:
            limiter.wait()
            try:
                candidates, total, elapsed = cpret.search(query)
            except CPRetError as exc:
                result.error = str(exc)
                return result
            except Exception as exc:  # 防御性：单题异常不影响其它题
                result.error = f"{type(exc).__name__}: {exc}"
                return result
            result_cache.store(query, candidates, total, elapsed)

        for candidate in candidates:
            apply_mapping(candidate)

        mains = [c for c in candidates if not c.is_duplicate]
        best = max(mains, key=lambda c: c.score) if mains else None
        result.candidates = candidates
        result.best = best
        if best is not None:
            result.chosen, result.note = _choose(best, candidates)
            if truncated:
                result.note = (result.note + "；" if result.note else "") + (
                    f"题面超过 {config.max_query_chars} 字符，已截断后查询"
                )
        return result

    workers = max(1, config.query_workers)
    _log(config, f"查询 CPRet：{len(problems)} 题（并发 {workers}，间隔 {config.delay:g}s）...",
         newline=True)
    results: list[MatchResult] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for index, result in enumerate(pool.map(process, problems), start=1):
            results.append(result)
            if not config.quiet:
                if result.error:
                    line = f"[{index}/{len(problems)}] {result.problem.pid} 失败：{result.error}"
                elif result.best is None:
                    line = f"[{index}/{len(problems)}] {result.problem.pid} CPRet 没有返回结果"
                else:
                    verdict = "命中" if result.matched else "无原题"
                    suffix = "（缓存）" if result.cached else ""
                    line = (
                        f"[{index}/{len(problems)}] {result.problem.pid} "
                        f"{result.best.score:.4f} {result.best.source} → {verdict}{suffix}"
                    )
                print(line, file=sys.stderr, flush=True)

    t_after_query = time.perf_counter()
    outcome = Outcome(target=target, config=config, problems=problems, results=results)
    _write_outputs(outcome)
    t_end = time.perf_counter()
    outcome.timings = {
        "login_list": t_after_list - t_start,
        "statements": t_after_fetch - t_after_list,
        "queries": t_after_query - t_after_fetch,
        "output": t_end - t_after_query,
        "total": t_end - t_start,
    }
    # JSON 里也记录阶段耗时，便于做性能对比。
    outcome.files["json"].write_text(
        json.dumps(outcome.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if config.timings:
        print(
            "耗时：登录/列表 {login_list:.2f}s，题面 {statements:.2f}s，"
            "CPRet {queries:.2f}s，输出 {output:.2f}s，总计 {total:.2f}s".format(
                **outcome.timings
            ),
            file=sys.stderr,
            flush=True,
        )
    return outcome


def _write_outputs(outcome: Outcome) -> None:
    config = outcome.config
    config.out_dir.mkdir(parents=True, exist_ok=True)
    tid = outcome.target.tid

    workbook = render_workbook(
        outcome.results,
        outcome.target,
        compact=config.compact_workbook,
        include_missing=config.include_missing,
    )
    report = render_report(
        outcome.results, outcome.target, config.threshold, top=config.top
    )
    data = json.dumps(outcome.to_dict(), ensure_ascii=False, indent=2)

    files = {
        "workbook": config.out_dir / f"vjudge-{tid}.md",
        "report": config.out_dir / f"report-{tid}.md",
        "json": config.out_dir / f"result-{tid}.json",
    }
    files["workbook"].write_text(workbook, encoding="utf-8")
    files["report"].write_text(report, encoding="utf-8")
    files["json"].write_text(data, encoding="utf-8")
    outcome.files = files


def summary_text(outcome: Outcome) -> str:
    return render_console(outcome.results, outcome.config.threshold)
