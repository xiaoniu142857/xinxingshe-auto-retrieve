"""Hydro OJ (信星社 OJ) client.

Hydro 5.x renders homework/contest pages on the server, so no undocumented API is
required: we log in through the normal ``POST /login`` form and scrape the problem
table plus each problem statement page.
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from urllib.parse import parse_qs, quote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

from .models import Problem

_TARGET_RE = re.compile(
    r"^(?P<origin>https?://[^/]+)/d/(?P<domain>[^/?#]+)/"
    r"(?P<kind>homework|contest|training)/(?P<tid>[0-9A-Za-z]+)"
)

_BLOCK_TAGS = {
    "p", "div", "section", "article", "h1", "h2", "h3", "h4", "h5", "h6",
    "li", "ul", "ol", "table", "tr", "td", "th", "pre", "blockquote",
    "figure", "figcaption", "details", "summary", "hr", "dl", "dt", "dd",
}

_SKIP_TAGS = {"script", "style", "svg", "iframe", "noscript", "button", "canvas"}


class HydroError(RuntimeError):
    """Fatal error while talking to the Hydro OJ."""


@dataclass(frozen=True)
class Target:
    origin: str
    domain: str
    kind: str
    tid: str
    page_url: str

    @property
    def label(self) -> str:
        names = {"homework": "作业", "contest": "比赛", "training": "训练"}
        return f"{names.get(self.kind, '页面')} {self.tid}"


def parse_target(url: str) -> Target:
    """Parse a Hydro homework/contest/training URL into its parts."""
    url = url.strip()
    m = _TARGET_RE.match(url)
    if not m:
        raise HydroError(
            "无法识别的链接。请传入形如 "
            "https://oj.xinxingshe.cn:444/d/xxs/homework/6af9fdc7470b12884211b21d 的页面。"
        )
    origin = m.group("origin").rstrip("/")
    domain = m.group("domain")
    kind = m.group("kind")
    tid = m.group("tid")
    page_url = f"{origin}/d/{domain}/{kind}/{tid}"
    return Target(origin=origin, domain=domain, kind=kind, tid=tid, page_url=page_url)


def _text_of_anchor(a: Tag, pid: str) -> str:
    raw = a.get_text(" ", strip=True).replace("\u00a0", " ")
    raw = re.sub(r"\s+", " ", raw).strip()
    if raw.startswith(pid):
        raw = raw[len(pid):].strip(" :：-")
    if not raw:
        return pid
    return raw


def _label_of_row(row: Tag | None) -> str:
    if row is None:
        return ""
    for cls in ("col--homework-relative-id", "col--problem-relative-id", "col--relative-id"):
        node = row.select_one(f".{cls}")
        if node:
            value = node.get_text(" ", strip=True)
            if value:
                return value
    return ""


def parse_problem_list(html: str, domain: str, origin: str) -> list[Problem]:
    """Extract the problem table from a Hydro homework/contest page."""
    soup = BeautifulSoup(html, "html.parser")
    pattern = re.compile(rf"/d/{re.escape(domain)}/p/([^/?#]+)")
    problems: list[Problem] = []
    seen: set[tuple[str, str]] = set()

    all_anchors: list[Tag] = []
    for a in soup.select("a[href]"):
        href = a.get("href") or ""
        if f"/d/{domain}/p/" in href and pattern.search(href):
            all_anchors.append(a)
    # 作业/比赛页的题目都在表格行里；优先只看表格，避免侧边栏推荐链接混入。
    # 训练等页面可能用卡片布局，此时退回全部链接。
    anchors = [a for a in all_anchors if a.find_parent("tr") is not None] or all_anchors

    for a in anchors:
        href = a.get("href") or ""
        m = pattern.search(href)
        if not m:
            continue
        pid = m.group(1)
        query = parse_qs(urlparse(href).query)
        tid = (query.get("tid") or [""])[0]
        key = (pid, tid)
        if key in seen:
            continue
        seen.add(key)
        title = _text_of_anchor(a, pid)
        row = a.find_parent("tr")
        problems.append(
            Problem(
                pid=pid,
                title=title,
                url=urljoin(origin + "/", href),
                tid=tid,
                label=_label_of_row(row),
            )
        )

    if not problems:
        raise HydroError(
            "作业页中没有解析到题目。可能尚未登录、没有访问权限，或页面结构已变化。"
        )
    return problems


def _walk(node: Tag) -> str:
    """Render a DOM subtree to text while keeping block structure and samples."""
    out: list[str] = []
    for child in node.children:
        if isinstance(child, NavigableString):
            # 行内文本压成单空格，避免源码缩进把一句话拆成多行；<pre> 单独处理。
            out.append(re.sub(r"\s+", " ", str(child)))
            continue
        if not isinstance(child, Tag):
            continue
        name = (child.name or "").lower()
        classes = child.get("class") or []
        if name in _SKIP_TAGS:
            continue
        if "katex-mathml" in classes:
            # KaTeX 会把同一公式存两份（MathML + 视觉层），只保留视觉层避免重复。
            continue
        if name == "br":
            out.append("\n")
        elif name == "pre":
            out.append("\n" + child.get_text() + "\n")
        elif name in _BLOCK_TAGS:
            out.append("\n" + _walk(child) + "\n")
        else:
            out.append(_walk(child))
    return "".join(out)


def _normalize_lines(raw: str) -> str:
    lines: list[str] = []
    for line in raw.splitlines():
        line = line.replace("\u00a0", " ").replace("\u200b", "").replace("\ufeff", "")
        line = re.sub(r"[ \t]+", " ", line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def extract_statement(html: str, title: str = "") -> str:
    """Extract the human-readable statement from a Hydro problem page."""
    soup = BeautifulSoup(html, "html.parser")
    content = soup.select_one("div.problem-content") or soup.select_one(".problem-content")
    if content is None:
        raise HydroError("题目页中找不到 problem-content，页面结构可能已变化。")

    text = _normalize_lines(_walk(content))
    if not text:
        raise HydroError("题目页的题面为空。")

    # 题面常把标题重复渲染两次，去掉开头的重复行。
    lines = text.splitlines()
    if title:
        norm_title = re.sub(r"\s+", " ", title).strip()
        while len(lines) >= 2 and lines[0] == norm_title and lines[1] == norm_title:
            lines.pop(0)
    return "\n".join(lines).strip()


class HydroClient:
    def __init__(
        self,
        target: Target,
        user: str,
        password: str,
        timeout: float = 30.0,
        retries: int = 3,
        session: requests.Session | None = None,
    ) -> None:
        self.target = target
        self.user = user
        self.password = password
        self.timeout = timeout
        self.retries = retries
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/143.0 Safari/537.36"
                ),
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
            }
        )
        # 登录后的抓题阶段会并发执行；requests.Session 不是线程安全的，
        # 因此每个工作线程使用复制了登录 Cookie 的独立 Session。
        self._local = threading.local()
        self._logged_in = False

    def _session(self) -> requests.Session:
        session = getattr(self._local, "session", None)
        if session is None:
            if self._logged_in and threading.current_thread() is not threading.main_thread():
                session = requests.Session()
                session.headers.update(self.session.headers)
                session.cookies.update(self.session.cookies)
            else:
                session = self.session
            self._local.session = session
        return session

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        kwargs.setdefault("timeout", self.timeout)
        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                return self._session().request(method, url, **kwargs)
            except requests.RequestException as exc:
                last_error = exc
                if attempt + 1 < self.retries:
                    time.sleep(1.0 + attempt)
        raise HydroError(f"请求 {url} 失败：{last_error}") from last_error

    def login(self) -> None:
        if not self.user or not self.password:
            raise HydroError("缺少用户名或密码。请用 --user/--password、环境变量或 .env 提供。")

        response = self._request(
            "POST",
            f"{self.target.origin}/login",
            data={
                "uname": self.user,
                "password": self.password,
                "rememberme": "on",
                "tfa": "",
                "authnChallenge": "",
            },
            # Hydro 登录成功会 302 到首页；跟随重定向会白白多抓一个首页。
            allow_redirects=False,
        )
        if response.status_code not in (200, 301, 302, 303, 307, 308):
            raise HydroError(f"登录失败：HTTP {response.status_code}。")
        if "sid" not in self.session.cookies:
            raise HydroError("登录失败：没有拿到 sid 会话，请检查用户名/密码。")
        self._logged_in = True

    def fetch_problems(self) -> list[Problem]:
        response = self._request("GET", self.target.page_url)
        if response.status_code in (401, 403) or "/login" in urlparse(response.url).path:
            raise HydroError(
                f"无法访问 {self.target.page_url}（HTTP {response.status_code}）。"
                "请确认账号有该作业/比赛的访问权限。"
            )
        if response.status_code != 200:
            raise HydroError(f"作业页返回 HTTP {response.status_code}。")
        return parse_problem_list(response.text, self.target.domain, self.target.origin)

    def fetch_statement(self, problem: Problem) -> str:
        url = f"{self.target.origin}/d/{self.target.domain}/p/{quote(problem.pid, safe='')}"
        if problem.tid:
            url += f"?tid={quote(problem.tid, safe='')}"
        response = self._request("GET", url)
        if response.status_code in (401, 403) or "/login" in urlparse(response.url).path:
            raise HydroError(f"无权查看题目 {problem.pid}（HTTP {response.status_code}）。")
        if response.status_code != 200:
            raise HydroError(f"题目 {problem.pid} 返回 HTTP {response.status_code}。")
        return extract_statement(response.text, problem.title)
