import unittest

from xinxingshe_auto_retrieve.cpret import parse_results

RESULTS_HTML = """
<ol class="result-list">
  <li class="result-card">
    <span class="rank medal-gold">#1</span>
    <a class="result-title" href="https://codeforces.com/problemset/problem/526/F">Pudding Monsters</a>
    <span class="oj-tag">Codeforces</span>
    <span class="score-num">0.8244</span>
    <details class="dups">
      <summary>另有 1 个同题</summary>
      <ul>
        <li>
          <span class="oj-tag">Luogu</span>
          <a class="t" href="https://www.luogu.com.cn/problem/P6256">布丁怪兽</a>
          <span class="num">0.8100</span>
        </li>
      </ul>
    </details>
  </li>
  <li class="result-card">
    <span class="rank medal-gold">#2</span>
    <a class="result-title" href="https://atcoder.jp/contests/abc311/tasks/abc311_e">[ABC311E] Defect-free Squares</a>
    <span class="oj-tag">AtCoder</span>
    <span class="score-num">0.6320</span>
  </li>
</ol>
"""


class TestParseResults(unittest.TestCase):
    def test_scores_and_duplicates(self):
        candidates = parse_results(RESULTS_HTML)
        mains = [c for c in candidates if not c.is_duplicate]
        dups = [c for c in candidates if c.is_duplicate]
        self.assertEqual(len(mains), 2)
        self.assertEqual(len(dups), 1)
        self.assertEqual(mains[0].title, "Pudding Monsters")
        self.assertEqual(mains[0].source, "Codeforces")
        self.assertAlmostEqual(mains[0].score, 0.8244)
        self.assertEqual(dups[0].source, "Luogu")
        self.assertAlmostEqual(dups[0].score, 0.8100)
        self.assertEqual(dups[0].group, mains[0].group)

    def test_empty(self):
        self.assertEqual(parse_results("<div>no results</div>"), [])

    def test_sample_cards_ignored(self):
        html = """
        <ol class="result-list">
          <li class="result-card sample-card">
            <a class="result-title" href="https://example.com">Sample</a>
            <span class="score-num">100%</span>
          </li>
        </ol>
        """
        self.assertEqual(parse_results(html), [])


if __name__ == "__main__":
    unittest.main()
