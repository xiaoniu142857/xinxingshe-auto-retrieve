import unittest

from xinxingshe_auto_retrieve.hydro import Target
from xinxingshe_auto_retrieve.models import Candidate, MatchResult, Problem
from xinxingshe_auto_retrieve.render import render_workbook


def make_result(token: str | None) -> MatchResult:
    problem = Problem(pid="P1", title="题目一", url="https://example.com/p/1", label="A")
    result = MatchResult(problem=problem, threshold=0.7)
    candidate = Candidate(
        title="原题", source="Codeforces", url="https://codeforces.com/problemset/problem/1/A",
        score=0.9,
    )
    if token:
        candidate.vjudge_oj, candidate.vjudge_num = token.split("-")[0], token.split("-")[1]
    result.best = candidate
    result.chosen = candidate
    return result


TARGET = Target(
    origin="https://oj.example.com",
    domain="xxs",
    kind="homework",
    tid="abc",
    page_url="https://oj.example.com/d/xxs/homework/abc",
)


class TestWorkbook(unittest.TestCase):
    def test_compact(self):
        results = [make_result("CodeForces-1A"), make_result("洛谷-P1001")]
        text = render_workbook(results, TARGET)
        self.assertEqual(text, "[problem:CodeForces-1A]\n[problem:洛谷-P1001]\n")

    def test_compact_skips_unmapped(self):
        results = [make_result(None), make_result("CodeForces-1A")]
        text = render_workbook(results, TARGET)
        self.assertEqual(text, "[problem:CodeForces-1A]\n")

    def test_full(self):
        results = [make_result("CodeForces-1A")]
        text = render_workbook(results, TARGET, compact=False, include_missing=False)
        self.assertIn("## A 题目一", text)
        self.assertIn("[problem:CodeForces-1A]", text)


if __name__ == "__main__":
    unittest.main()
