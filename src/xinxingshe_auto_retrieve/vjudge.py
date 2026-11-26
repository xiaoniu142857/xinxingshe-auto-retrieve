"""Map CPRet results to VJudge problem tokens.

VJudge workbooks embed problems with ``[problem:<OJ key>-<problem number>]``.
The OJ keys are *not* always the display names: Luogu is ``洛谷``, Nowcoder is
``牛客`` and UOJ is ``UniversalOJ`` (see https://vjudge.net/util/cfg).
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from .models import Candidate

SOURCE_TO_OJ: dict[str, str] = {
    "Aizu": "Aizu",
    "AIZU": "Aizu",
    "AtCoder": "AtCoder",
    "BZOJ": "BZOJ",
    "CodeChef": "CodeChef",
    "Codeforces": "CodeForces",
    "CodeforcesGym": "Gym",
    "Gym": "Gym",
    "LibreOJ": "LibreOJ",
    "Luogu": "洛谷",
    "Nowcoder": "牛客",
    "NowCoder": "牛客",
    "QOJ": "QOJ",
    "SPOJ": "SPOJ",
    "UOJ": "UniversalOJ",
    "UniversalOJ": "UniversalOJ",
    "CSES": "CSES",
    "HDU": "HDU",
    "POJ": "POJ",
    "UVA": "UVA",
    "UVALive": "UVALive",
    "ZOJ": "ZOJ",
    "HYSBZ": "HYSBZ",
    "51Nod": "51Nod",
    "HihoCoder": "HihoCoder",
    "Kattis": "Kattis",
    "TopCoder": "TopCoder",
    "Yukicoder": "Yukicoder",
    "Baekjoon": "Baekjoon",
}

# OJ 键虽然存在，但在 VJudge 上已停服或无法取题。
DEAD_OJS = {
    "BZOJ": "VJudge 的 BZOJ 已停止服务",
}

# CPRet 题目库里包含、但 VJudge 题单不支持直接嵌入的 OJ。
UNSUPPORTED_SOURCES = {
    "Hydro": "VJudge 不支持 Hydro 题号",
    "LeetCode": "VJudge 不支持 LeetCode 题号",
}


def parse_prob_num(source: str, url: str) -> str | None:
    """Derive the VJudge problem number from the original problem URL."""
    path = urlparse(url).path.rstrip("/")
    source = SOURCE_TO_OJ.get(source, source)

    if source == "CodeForces":
        for pattern in (
            r"/problemset/problem/(\d+)/([A-Za-z][A-Za-z0-9]*)",
            r"/contest/(\d+)/problem/([A-Za-z][A-Za-z0-9]*)",
        ):
            m = re.search(pattern, path)
            if m:
                return m.group(1) + m.group(2)

    if source == "Gym":
        for pattern in (
            r"/gym/(\d+)/problem/([A-Za-z0-9]+)",
            r"/problemset/gymProblem/(\d+)/([A-Za-z0-9]+)",
        ):
            m = re.search(pattern, path)
            if m:
                return m.group(1) + m.group(2)

    if source == "AtCoder":
        m = re.search(r"/tasks/([^/]+)", path)
        if m:
            return m.group(1)
        m = re.search(r"/contests/([^/]+)/tasks/([^/]+)", path)
        if m:
            return m.group(2)

    if source == "洛谷":
        m = re.search(r"/problem/([A-Za-z0-9_]+)", path)
        if m:
            return m.group(1)

    if source == "牛客":
        for pattern in (r"/acm/problem/(\d+)", r"/problem/(\d+)"):
            m = re.search(pattern, path)
            if m:
                return m.group(1)

    if source in {"LibreOJ", "QOJ", "UniversalOJ"}:
        m = re.search(r"/problem/(\d+)", path) or re.search(r"/p/(\d+)", path)
        if m:
            return m.group(1)

    if source == "SPOJ":
        m = re.search(r"/problems/([A-Za-z0-9_]+)", path)
        if m:
            return m.group(1)

    if source == "CodeChef":
        m = re.search(r"/problems/([A-Za-z0-9_]+)", path)
        if m:
            return m.group(1)

    if source == "Aizu":
        m = re.search(r"/problems/([A-Za-z0-9_]+)", path)
        if m:
            return m.group(1)

    if source == "BZOJ":
        m = re.search(r"/p/(?:bzoj-)?(?:P)?(\d+)", path) or re.search(r"id=(\d+)", url)
        if m:
            return m.group(1)

    return None


def apply_mapping(candidate: Candidate) -> str | None:
    """Fill ``candidate.vjudge_oj/num``; return an explanatory note when unmapped."""
    oj_key = SOURCE_TO_OJ.get(candidate.source)
    if oj_key is None:
        note = UNSUPPORTED_SOURCES.get(
            candidate.source, f"VJudge 题单不支持来源 {candidate.source or '未知'}"
        )
        return note
    if oj_key in DEAD_OJS:
        return DEAD_OJS[oj_key]

    num = parse_prob_num(candidate.source, candidate.url)
    if not num:
        return f"无法从链接识别 {candidate.source} 的题号"
    candidate.vjudge_oj = oj_key
    candidate.vjudge_num = num
    return None
