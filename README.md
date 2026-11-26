# xinxingshe-auto-retrieve

抓取 **信星社 OJ**（Hydro，`oj.xinxingshe.cn:444`）作业页里的全部题目，送入
[CPRet](https://cpret.online/) 做「原题查询」，再把命中的原题转换成
**VJudge 题单**可直接使用的格式。

- 相似度最高的题目 `score > threshold`（默认 `0.7`）→ 判定为原题
- 否则 → 报告「无原题」，并保留最高相似度供人工复核
- 输出 VJudge workbook 正文，题目使用 `[problem:OJ-题号]` 语法，可整段粘贴

## 环境

需要 [uv](https://docs.astral.sh/uv/)。项目由 uv 管理（`pyproject.toml` + `uv.lock`）。

```bash
uv sync
```

## 配置账号

方式一（推荐）：复制 `.env.example` 为 `.env`，填写：

```dotenv
XXS_USER=（你的用户名）
XXS_PASSWORD=（密码）
```

方式二：命令行传入 `--user/--password`，或设置环境变量 `XXS_USER` / `XXS_PASSWORD`。
`.env` 已在 `.gitignore` 中，不会被提交。

## 用法

```bash
uv run oj2vjudge "https://oj.xinxingshe.cn:444/d/xxs/homework/6af9fdc7470b12884211b21d"
```

常用参数：

| 参数 | 说明 |
|---|---|
| `--threshold 0.7` | 判定原题的相似度阈值（严格大于） |
| `--out-dir output` | 输出目录 |
| `--only Day2P1,火灾` | 只处理匹配题号/相对编号/标题的题目 |
| `--max-problems 3` | 只处理前 3 题，便于调试 |
| `--dry-run` | 只抓题目列表，不查询 CPRet |
| `--refresh` | 忽略并刷新题面缓存与 CPRet 结果缓存 |
| `--delay 0.4` | CPRet 查询的全局最小间隔（秒） |
| `--workers 6` | 并发抓取题面的线程数 |
| `--query-workers 3` | 并发查询 CPRet 的线程数 |
| `--cache-ttl 14` | CPRet 结果缓存有效期（天），`0` 关闭 |
| `--no-result-cache` | 不使用 CPRet 结果缓存 |
| `--timings` | 打印登录/抓题/查询/输出各阶段耗时 |
| `--no-missing` | 完整题单模式下不附「未找到原题」的附录 |
| `--full-workbook` | 题单带标题/附录；默认只输出紧凑的 `[problem:...]` 行 |
| `-q` | 安静模式，不显示逐题进度 |

示例：先看看这周作业有哪些题：

```bash
uv run oj2vjudge "https://oj.xinxingshe.cn:444/d/xxs/homework/6af9fdc7470b12884211b21d" --dry-run
```

只测前两题：

```bash
uv run oj2vjudge "https://oj.xinxingshe.cn:444/d/xxs/homework/6af9fdc7470b12884211b21d" --max-problems 2 --refresh
```

## 输出

运行后在 `output/` 生成三个文件：

| 文件 | 内容 |
|---|---|
| `vjudge-<作业ID>.md` | **VJudge 题单正文**，一行一个 `[problem:OJ-题号]`，紧凑格式 |
| `report-<作业ID>.md` | 每题的最高相似度、候选题目、判定结论 |
| `result-<作业ID>.json` | 完整结构化数据，便于二次处理 |

`vjudge-<作业ID>.md` 默认只包含题目 token，可直接整段粘贴：

```markdown
[problem:CodeForces-526F]
[problem:QOJ-2502]
[problem:CodeForces-1553H]
```

需要带标题和“未找到原题”附录时，加 `--full-workbook`。

### 如何导入 VJudge

1. 打开 <https://vjudge.net/workbook>，新建题单（或编辑已有题单）；
2. 把 `vjudge-<作业ID>.md` 的**全部内容**粘贴进题单正文（支持 Markdown）；
3. 保存后，`[problem:...]` 会被渲染成对应 OJ 的题目卡片，并自动生成目录。

VJudge 的题单正文本身就是一个 Markdown 文档；`[problem:CodeForces-526F]`
这种写法是 VJudge 官方的题目引用语法（`OJ键-题号`）。

## 性能

23 题作业的实测（同一台机器、同一网络）：

| 场景 | 耗时 |
|---|---|
| 优化前（串行抓题 + 串行查询） | 约 26 秒 |
| 冷启动（`--refresh`，并发抓题 + 并发查询） | 约 12 秒 |
| 热缓存（题面与查询结果均命中） | 约 1–2 秒（内部约 0.5 秒） |

实现方式：

- 题面用线程池并发抓取（默认 6 线程）；
- CPRet 查询用线程池并发（默认 3 线程），并用全局限速器保证请求间隔不小于
  `--delay`（默认 0.4 秒），不会因为并发而高频冲击对方服务；
- 题面缓存在 `.cache/<domain>-<tid>.json`，CPRet 结果按查询文本哈希缓存在
  `.cache/cpret/*.json`，默认有效期 14 天；
- `--refresh` 只绕过旧缓存，仍会把新结果写回缓存；
- `--timings` 可以打印各阶段耗时，方便按机器/网络调参。

如果网络条件好，可适当提高并发、降低间隔：

```bash
uv run oj2vjudge "<作业链接>" --query-workers 4 --delay 0.25
```

## OJ 映射

CPRet 的来源名与 VJudge 的 OJ 键并不总是一致，本项目内置了映射：

| CPRet 来源 | VJudge 键 | 题号来源 |
|---|---|---|
| Codeforces | `CodeForces` | 比赛号 + 题号，如 `526F` |
| CodeforcesGym | `Gym` | Gym 号 + 题号，如 `102001A` |
| AtCoder | `AtCoder` | task id，如 `abc311_e` |
| Luogu | `洛谷` | `P1440` |
| Nowcoder | `牛客` | 数字题号 |
| LibreOJ | `LibreOJ` | 数字题号 |
| UOJ | `UniversalOJ` | 数字题号 |
| QOJ | `QOJ` | 数字题号 |
| SPOJ / CodeChef / Aizu | 同名 | 原题号 |
| BZOJ | 不输出 | VJudge 的 BZOJ 已停服 |
| Hydro / LeetCode | 不输出 | VJudge 不支持其题号 |

如果 CPRet 返回的最高分题目恰好来自 VJudge 不支持的 OJ，程序会自动在同题的
「重复题」分组里寻找可用的 OJ 版本（例如 Luogu 上的同题），并在报告里注明。

## 工作原理

1. **抓题**：用账号 `POST /login` 登录 Hydro，抓取作业/比赛页的题目表格，再并发抓取
   `problem-content` 题面（清理 KaTeX 的重复公式层、保留样例换行）。
2. **查原题**：把「标题 + 题面」`POST` 到 `https://cpret.online/api/search`，解析返回的
   结果卡片：`score-num`（余弦相似度）、`oj-tag`、`result-title` 链接，以及折叠的重复题。
3. **转换**：按 OJ 规则从原题 URL 提取题号，拼成 `[problem:OJ键-题号]`。
4. **输出**：控制台总览 + Markdown 报告 + VJudge 题单 + JSON。

题面会缓存在 `.cache/<domain>-<tid>.json`，CPRet 查询结果按题面哈希缓存在
`.cache/cpret/`，重复运行不必重新抓取或重新查询（`--refresh` 可强制刷新）。

## 说明与限制

- 仅用于个人学习、题目对照。请遵守信星社 OJ 与 CPRet 的使用条款，不要高频请求；
  默认查询间隔 0.4 秒、并发 3 路，已尽量温和。
- CPRet 的相似度是向量余弦值，同一道题在不同翻译/改写下的得分会有波动；阈值
  `0.7` 是经验值，可用 `--threshold` 调整。
- 题面超过 `--max-query-chars`（默认 8000）会被截断，报告里会注明。
- 若作业页改版或需要额外权限，抓取会给出明确错误；登录失败通常是密码错误或站点风控。
- VJudge 的键名来自 <https://vjudge.net/util/cfg> 的 `remoteOJs`，如果 VJudge 后续调整，
  只需修改 `src/xinxingshe_auto_retrieve/vjudge.py` 中的映射表。
- 本项目使用 GPL-3.0 许可证（见 `LICENSE`）。

## 开发

```bash
uv run python -m unittest discover -s tests -v
```
