import unittest

from xinxingshe_auto_retrieve.models import Candidate
from xinxingshe_auto_retrieve.pipeline import _choose
from xinxingshe_auto_retrieve.vjudge import apply_mapping, parse_prob_num


def mapped(source, url, title="t"):
    cand = Candidate(title=title, source=source, url=url, score=0.9)
    apply_mapping(cand)
    return cand


class TestParseProbNum(unittest.TestCase):
    def test_codeforces(self):
        self.assertEqual(
            parse_prob_num("Codeforces", "https://codeforces.com/problemset/problem/526/F"),
            "526F",
        )
        self.assertEqual(
            parse_prob_num("Codeforces", "https://codeforces.com/contest/1979/problem/A"),
            "1979A",
        )
        self.assertEqual(
            parse_prob_num("Codeforces", "https://codeforces.com/problemset/problem/2267/F1"),
            "2267F1",
        )

    def test_gym(self):
        self.assertEqual(
            parse_prob_num("CodeforcesGym", "https://codeforces.com/gym/102001/problem/A"),
            "102001A",
        )
        self.assertEqual(
            parse_prob_num("CodeforcesGym", "https://codeforces.com/problemset/gymProblem/102001/A"),
            "102001A",
        )

    def test_atcoder(self):
        self.assertEqual(
            parse_prob_num("AtCoder", "https://atcoder.jp/contests/abc311/tasks/abc311_e"),
            "abc311_e",
        )

    def test_other_ojs(self):
        self.assertEqual(
            parse_prob_num("Luogu", "https://www.luogu.com.cn/problem/P1440"), "P1440"
        )
        self.assertEqual(
            parse_prob_num("Nowcoder", "https://ac.nowcoder.com/acm/problem/207590"), "207590"
        )
        self.assertEqual(parse_prob_num("LibreOJ", "https://loj.ac/p/3256"), "3256")
        self.assertEqual(parse_prob_num("UOJ", "https://uoj.ac/problem/1094"), "1094")
        self.assertEqual(parse_prob_num("QOJ", "https://qoj.ac/problem/2502"), "2502")
        self.assertEqual(
            parse_prob_num("SPOJ", "https://www.spoj.com/problems/HISTOGRA/"), "HISTOGRA"
        )
        self.assertEqual(
            parse_prob_num("CodeChef", "https://www.codechef.com/problems/HXOR"), "HXOR"
        )
        self.assertEqual(
            parse_prob_num("Aizu", "https://onlinejudge.u-aizu.ac.jp/problems/ALDS1_1_A"),
            "ALDS1_1_A",
        )


class TestMapping(unittest.TestCase):
    def test_luogu_token(self):
        cand = mapped("Luogu", "https://www.luogu.com.cn/problem/P6256", "布丁怪兽")
        self.assertEqual(cand.vjudge_token, "[problem:洛谷-P6256]")

    def test_uoj_token(self):
        cand = mapped("UOJ", "https://uoj.ac/problem/1094")
        self.assertEqual(cand.vjudge_token, "[problem:UniversalOJ-1094]")

    def test_nowcoder_token(self):
        cand = mapped("Nowcoder", "https://ac.nowcoder.com/acm/problem/207590")
        self.assertEqual(cand.vjudge_token, "[problem:牛客-207590]")

    def test_codeforces_token(self):
        cand = mapped("Codeforces", "https://codeforces.com/problemset/problem/526/F")
        self.assertEqual(cand.vjudge_token, "[problem:CodeForces-526F]")

    def test_unsupported(self):
        cand = mapped("Hydro", "https://hydro.ac/p/xxs-P1001")
        self.assertIsNone(cand.vjudge_token)
        cand = mapped("LeetCode", "https://leetcode.cn/problems/two-sum/")
        self.assertIsNone(cand.vjudge_token)

    def test_bzoj_dead(self):
        cand = mapped("BZOJ", "https://hydro.ac/p/bzoj-P3705")
        self.assertIsNone(cand.vjudge_token)


class TestChoose(unittest.TestCase):
    def test_prefers_best(self):
        best = mapped("Codeforces", "https://codeforces.com/problemset/problem/526/F")
        chosen, note = _choose(best, [best])
        self.assertIs(chosen, best)
        self.assertEqual(note, "")

    def test_falls_back_to_duplicate(self):
        best = Candidate(title="A", source="Hydro", url="https://hydro.ac/p/x", score=0.9)
        dup = Candidate(
            title="A", source="Luogu", url="https://www.luogu.com.cn/problem/P1",
            score=0.88, group=0, is_duplicate=True,
        )
        apply_mapping(best)
        apply_mapping(dup)
        chosen, note = _choose(best, [best, dup])
        self.assertIs(chosen, dup)
        self.assertIn("同题版本", note)
        self.assertEqual(chosen.vjudge_token, "[problem:洛谷-P1]")

    def test_unmapped(self):
        best = Candidate(title="A", source="Hydro", url="https://hydro.ac/p/x", score=0.9)
        apply_mapping(best)
        chosen, note = _choose(best, [best])
        self.assertIs(chosen, best)
        self.assertIn("无法生成 VJudge 题号", note)


if __name__ == "__main__":
    unittest.main()
