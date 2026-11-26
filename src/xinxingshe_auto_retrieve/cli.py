"""Command-line interface."""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

from .cpret import CPRetError
from .hydro import HydroError
from .pipeline import Config, PipelineError, run, summary_text


def load_env_file(path: Path) -> None:
    """Tiny .env loader; existing environment variables win."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="oj2vjudge",
        description=(
            "抓取 Hydro OJ（信星社 OJ）作业页的全部题目，"
            "用 CPRet 查询原题，并输出可在 VJudge 题单中直接使用的格式。"
        ),
    )
    parser.add_argument(
        "url",
        help="作业/比赛页链接，例如 https://oj.xinxingshe.cn:444/d/xxs/homework/6af9fdc7470b12884211b21d",
    )
    parser.add_argument("--threshold", type=float, default=0.7,
                        help="判定原题的最低相似度（严格大于），默认 0.7")
    parser.add_argument("--out-dir", type=Path, default=Path("output"),
                        help="输出目录，默认 ./output")
    parser.add_argument("--cache-dir", type=Path, default=Path(".cache"),
                        help="题面缓存目录，默认 ./.cache")
    parser.add_argument("--user", default=os.environ.get("XXS_USER"),
                        help="OJ 用户名，默认读取环境变量 XXS_USER")
    parser.add_argument("--password", default=os.environ.get("XXS_PASSWORD"),
                        help="OJ 密码，默认读取环境变量 XXS_PASSWORD；缺省时交互输入")
    parser.add_argument("--env-file", type=Path, default=Path(".env"),
                        help="从该文件读取 XXS_USER / XXS_PASSWORD，默认 ./.env")
    parser.add_argument("--delay", type=float, default=0.4,
                        help="CPRet 查询的全局最小间隔秒数，默认 0.4")
    parser.add_argument("--workers", type=int, default=6,
                        help="抓取题面的并发线程数，默认 6")
    parser.add_argument("--query-workers", type=int, default=3,
                        help="CPRet 查询并发数，默认 3")
    parser.add_argument("--cache-ttl", type=float, default=14.0,
                        help="CPRet 结果缓存有效期（天），0 表示关闭，默认 14")
    parser.add_argument("--no-result-cache", dest="result_cache", action="store_false",
                        help="不使用 CPRet 结果缓存（题面缓存仍生效）")
    parser.add_argument("--timings", action="store_true",
                        help="运行结束后打印各阶段耗时")
    parser.add_argument("--timeout", type=float, default=30.0,
                        help="访问 OJ 的超时秒数，默认 30")
    parser.add_argument("--cpret-timeout", type=float, default=180.0,
                        help="CPRet 查询超时秒数，默认 180")
    parser.add_argument("--max-query-chars", type=int, default=8000,
                        help="送入 CPRet 的题面最大字符数，默认 8000")
    parser.add_argument("--top", type=int, default=3,
                        help="报告中每题展示的候选数量，默认 3")
    parser.add_argument("--only", action="append", metavar="TEXT",
                        help="只处理匹配的题目（按题号/相对编号/标题子串，可逗号分隔，可重复）")
    parser.add_argument("--max-problems", type=int,
                        help="最多处理前 N 题（调试用）")
    parser.add_argument("--refresh", action="store_true",
                        help="忽略并刷新题面缓存与 CPRet 结果缓存")
    parser.add_argument("--dry-run", action="store_true",
                        help="只抓取并列出题目，不查询 CPRet")
    parser.add_argument("--no-missing", dest="include_missing", action="store_false",
                        help="完整题单模式下不附带“未找到原题”的附录")
    parser.add_argument("--full-workbook", dest="compact_workbook", action="store_false",
                        help="题单带标题和附录；默认只输出一行一个 [problem:...] 的紧凑格式")
    parser.add_argument("-q", "--quiet", action="store_true", help="不显示抓取进度")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    load_env_file(args.env_file)
    # load_env_file 只在变量不存在时写入，所以这里重新取一次。
    user = args.user or os.environ.get("XXS_USER")
    password = args.password or os.environ.get("XXS_PASSWORD")

    if not (0.0 <= args.threshold <= 1.0):
        parser.error("--threshold 必须在 0 到 1 之间")
    if args.delay < 0:
        parser.error("--delay 不能为负数")
    if args.workers < 1:
        parser.error("--workers 至少为 1")
    if args.query_workers < 1:
        parser.error("--query-workers 至少为 1")
    if args.cache_ttl < 0:
        parser.error("--cache-ttl 不能为负数")
    if not user:
        parser.error("缺少 OJ 用户名：请用 --user、XXS_USER 或 .env 提供")
    if not password:
        if not sys.stdin.isatty():
            parser.error("缺少 OJ 密码：请用 --password、XXS_PASSWORD 或 .env 提供")
        password = getpass.getpass(f"{user} 的 OJ 密码：")

    only: list[str] = []
    for item in args.only or []:
        only.extend(part.strip() for part in item.split(",") if part.strip())

    config = Config(
        url=args.url,
        user=user,
        password=password,
        threshold=args.threshold,
        out_dir=args.out_dir,
        cache_dir=args.cache_dir,
        delay=args.delay,
        timeout=args.timeout,
        cpret_timeout=args.cpret_timeout,
        max_query_chars=args.max_query_chars,
        top=args.top,
        refresh=args.refresh,
        only=only,
        dry_run=args.dry_run,
        quiet=args.quiet,
        include_missing=args.include_missing,
        compact_workbook=args.compact_workbook,
        max_problems=args.max_problems,
        fetch_workers=args.workers,
        query_workers=args.query_workers,
        result_cache=args.result_cache,
        cache_ttl_days=args.cache_ttl,
        timings=args.timings,
    )

    try:
        outcome = run(config)
    except (HydroError, PipelineError, CPRetError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\n已中断。", file=sys.stderr)
        return 130

    if config.dry_run:
        print(f"共抓取到 {len(outcome.problems)} 题：")
        for problem in outcome.problems:
            label = f"[{problem.label}] " if problem.label else ""
            print(f"  {problem.pid}  {label}{problem.title}")
        return 0

    print()
    print(summary_text(outcome))
    print()
    print("已生成文件：")
    print(f"  VJudge 题单：{outcome.files['workbook']}")
    print(f"  查询报告：  {outcome.files['report']}")
    print(f"  JSON 数据： {outcome.files['json']}")
    print()
    print(
        "用法：打开 https://vjudge.net/workbook ，新建或编辑题单，"
        "把 VJudge 题单文件的内容粘贴到题单正文即可。"
    )
    return 0
