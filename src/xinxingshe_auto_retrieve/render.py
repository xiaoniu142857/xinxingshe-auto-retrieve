"""Console / Markdown renderers."""

from __future__ import annotations

import unicodedata
from datetime import datetime

from .hydro import Target
from .models import Candidate, MatchResult


def _char_width(ch: str) -> int:
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def text_width(text: str) -> int:
    return sum(_char_width(ch) for ch in text)


def truncate(text: str, width: int) -> str:
    if text_width(text) <= width:
        return text
    out: list[str] = []
    used = 0
    for ch in text:
        w = _char_width(ch)
        if used + w > width - 1:
            break
        out.append(ch)
        used += w
    return "".join(out) + "…"


def pad(text: str, width: int, align: str = "left") -> str:
    gap = max(0, width - text_width(text))
    if align == "right":
        return " " * gap + text
    return text + " " * gap


def status_of(result: MatchResult) -> str:
    if result.error:
        return "失败"
    if not result.matched:
        return "无原题"
    if result.token:
        return "命中*" if result.chosen and result.chosen.is_duplicate else "命中"
    return "未映射"


def vjudge_name(candidate: Candidate | None) -> str:
    if candidate and candidate.vjudge_oj and candidate.vjudge_num:
        return f"{candidate.vjudge_oj}-{candidate.vjudge_num}"
    return "-"


def render_console(results: list[MatchResult], threshold: float) -> str:
    header = "  ".join(
        [
            pad("序号", 4),
            pad("题号", 6),
            pad("题目", 38),
            pad("相似度", 8, "right"),
            pad("结论", 9),
            "VJudge",
        ]
    )
    lines = [header, "-" * 88]
    for index, result in enumerate(results, start=1):
        score = f"{result.best.score:.4f}" if result.best else "-"
        row = "  ".join(
            [
                pad(str(index), 4),
                pad(result.problem.label or "-", 6),
                pad(truncate(result.problem.title, 37), 38),
                pad(score, 8, "right"),
                pad(status_of(result), 9),
                vjudge_name(result.chosen if result.token else None),
            ]
        )
        lines.append(row)
    matched = sum(1 for r in results if r.matched)
    unmapped = sum(1 for r in results if r.matched and not r.token)
    failed = sum(1 for r in results if r.error)
    lines.append("-" * 84)
    lines.append(
        f"共 {len(results)} 题：命中 {matched} 题"
        f"（其中 {unmapped} 题无法生成 VJudge 题号），"
        f"无原题 {len(results) - matched - failed} 题，失败 {failed} 题。阈值 {threshold:g}。"
    )
    return "\n".join(lines)


def _candidate_rows(candidates: list[Candidate], limit: int) -> list[str]:
    mains = [c for c in candidates if not c.is_duplicate]
    rows = []
    for index, cand in enumerate(mains[:limit], start=1):
        rows.append(
            f"| {index} | {cand.source} | {cand.title} | {cand.score:.4f} | "
            f"[打开]({cand.url}) | {vjudge_name(cand)} |"
        )
    return rows


def render_report(
    results: list[MatchResult],
    target: Target,
    threshold: float,
    *,
    top: int = 3,
) -> str:
    matched = sum(1 for r in results if r.matched)
    lines = [
        "# CPRet 原题查询报告",
        "",
        f"- 来源页面：{target.page_url}",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 相似度阈值：{threshold:g}（严格大于该值才判定为原题）",
        f"- 统计：共 {len(results)} 题，命中 {matched} 题，"
        f"无原题 {len(results) - matched} 题。",
        "",
        "## 总览",
        "",
        "| # | 题号 | 题目 | 最高相似度 | 结论 | VJudge 题号 |",
        "|---|---|---|---|---|---|",
    ]
    for index, result in enumerate(results, start=1):
        score = f"{result.best.score:.4f}" if result.best else "-"
        token = result.token or "-"
        lines.append(
            f"| {index} | {result.problem.label or '-'} | "
            f"[{result.problem.title}]({result.problem.url}) | {score} | "
            f"{status_of(result)} | `{token}` |"
        )

    lines += ["", "## 各题详情", ""]
    for index, result in enumerate(results, start=1):
        heading = f"{result.problem.label + ' ' if result.problem.label else ''}{result.problem.title}"
        lines.append(f"### {index}. {heading}")
        lines.append("")
        lines.append(f"- 原题页面：{result.problem.url}")
        if result.error:
            lines.append(f"- 错误：{result.error}")
        if result.best:
            lines.append(
                f"- 最高相似度：**{result.best.score:.4f}** — "
                f"{result.best.source} / [{result.best.title}]({result.best.url})"
            )
            lines.append(f"- 判定：{status_of(result)}" + (f"（{result.note}）" if result.note else ""))
        else:
            lines.append("- CPRet 没有返回任何结果。")
        if result.token:
            lines.append(f"- VJudge token：`{result.token}`")
        if result.chosen and result.chosen.is_duplicate:
            lines.append(
                f"- 采用同题版本：{result.chosen.source} "
                f"[{result.chosen.title}]({result.chosen.url})（{result.chosen.score:.4f}）"
            )
        if result.candidates:
            lines += ["", "<details>", "<summary>候选结果</summary>", "",
                      "| # | OJ | 题目 | 相似度 | 链接 | VJudge |",
                      "|---|---|---|---|---|---|"]
            lines += _candidate_rows(result.candidates, top)
            lines += ["", "</details>"]
        lines.append("")
    return "\n".join(lines)


def render_workbook(
    results: list[MatchResult],
    target: Target,
    *,
    compact: bool = True,
    include_missing: bool = True,
) -> str:
    """Render a VJudge workbook body using ``[problem:OJ-题号]`` tokens.

    ``compact=True`` 时只输出一行一个 token，便于直接整段粘贴到题单正文。
    """
    tokens = [r.token for r in results if r.token]
    if compact:
        return "\n".join(tokens) + ("\n" if tokens else "")

    lines = [
        f"# 信星社 OJ 原题题单（{target.label}）",
        "",
        f"来源：{target.page_url}",
        "",
    ]
    for result in results:
        if not result.token:
            continue
        prefix = f"{result.problem.label} " if result.problem.label else ""
        lines.append(f"## {prefix}{result.problem.title}")
        lines.append(result.token)
        lines.append("")

    if include_missing:
        missing = [r for r in results if not r.token]
        if missing:
            lines += ["## 未找到原题 / 无法映射", ""]
            for result in missing:
                prefix = f"{result.problem.label} " if result.problem.label else ""
                lines.append(f"### {prefix}{result.problem.title}")
                if result.error:
                    lines.append(f"处理失败：{result.error}")
                elif result.best:
                    lines.append(
                        f"最高相似度 {result.best.score:.4f} — "
                        f"{result.best.source} [{result.best.title}]({result.best.url})"
                    )
                    if result.note:
                        lines.append(result.note)
                else:
                    lines.append("CPRet 未返回结果。")
                lines.append(f"[原题页面]({result.problem.url})")
                lines.append("")
    return "\n".join(lines).rstrip() + "\n"
