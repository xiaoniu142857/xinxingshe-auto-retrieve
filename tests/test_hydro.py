import unittest

from xinxingshe_auto_retrieve.hydro import (
    HydroError,
    extract_statement,
    parse_problem_list,
    parse_target,
)

HOMEWORK_HTML = """
<html><body>
<table><tbody>
<tr>
  <td class="col--status">没有递交</td>
  <td class="col--homework-relative-id"><span>A</span></td>
  <td class="col--problem">
    <a href="/d/xxs/p/Day2P1?tid=6af9fdc7470b12884211b21d"><b>Day2P1</b> &nbsp;&nbsp;Day2-1 布丁怪兽</a>
  </td>
</tr>
<tr>
  <td class="col--status">没有递交</td>
  <td class="col--homework-relative-id"><span>B</span></td>
  <td class="col--problem">
    <a href="/d/xxs/p/119?tid=6af9fdc7470b12884211b21d"><b>119</b> &nbsp;&nbsp;Day2-21 括号匹配</a>
  </td>
</tr>
</tbody></table>
</body></html>
"""

STATEMENT_HTML = """
<html><body>
<div class="problem-content">
  <h1>Day2-1 布丁怪兽</h1>
  <h1>Day2-1 布丁怪兽</h1>
  <p>地图是一个
    <span class="katex">
      <span class="katex-mathml"><math><annotation>n\\times n</annotation></math></span>
      <span class="katex-html">n×n</span>
    </span>
    的方格。</p>
  <p>样例输入：</p>
  <pre>5
1 1
4 3</pre>
</div>
</body></html>
"""


class TestParseTarget(unittest.TestCase):
    def test_homework(self):
        target = parse_target(
            "https://oj.xinxingshe.cn:444/d/xxs/homework/6af9fdc7470b12884211b21d"
        )
        self.assertEqual(target.origin, "https://oj.xinxingshe.cn:444")
        self.assertEqual(target.domain, "xxs")
        self.assertEqual(target.kind, "homework")
        self.assertEqual(target.tid, "6af9fdc7470b12884211b21d")
        self.assertEqual(
            target.page_url,
            "https://oj.xinxingshe.cn:444/d/xxs/homework/6af9fdc7470b12884211b21d",
        )

    def test_trailing_slash_and_query(self):
        target = parse_target(
            "https://oj.xinxingshe.cn:444/d/xxs/homework/abc123/?from=share"
        )
        self.assertEqual(target.tid, "abc123")

    def test_invalid(self):
        with self.assertRaises(HydroError):
            parse_target("https://oj.xinxingshe.cn:444/p/P1001")


class TestProblemList(unittest.TestCase):
    def test_parse(self):
        problems = parse_problem_list(
            HOMEWORK_HTML, "xxs", "https://oj.xinxingshe.cn:444"
        )
        self.assertEqual(len(problems), 2)
        first, second = problems
        self.assertEqual(first.pid, "Day2P1")
        self.assertEqual(first.title, "Day2-1 布丁怪兽")
        self.assertEqual(first.label, "A")
        self.assertEqual(
            first.url,
            "https://oj.xinxingshe.cn:444/d/xxs/p/Day2P1?tid=6af9fdc7470b12884211b21d",
        )
        self.assertEqual(second.pid, "119")
        self.assertEqual(second.title, "Day2-21 括号匹配")
        self.assertEqual(second.label, "B")


class TestStatement(unittest.TestCase):
    def test_extract(self):
        text = extract_statement(STATEMENT_HTML, "Day2-1 布丁怪兽")
        self.assertNotIn("n\\times n", text)
        self.assertEqual(text.count("n×n"), 1)
        self.assertIn("地图是一个 n×n 的方格。", text)
        self.assertIn("5\n1 1\n4 3", text)
        self.assertFalse(text.startswith("Day2-1 布丁怪兽\nDay2-1 布丁怪兽"))

    def test_missing_content(self):
        with self.assertRaises(HydroError):
            extract_statement("<html><body><p>no content</p></body></html>")


if __name__ == "__main__":
    unittest.main()
