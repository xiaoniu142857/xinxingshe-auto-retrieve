import shutil
import unittest
import uuid
from pathlib import Path

from xinxingshe_auto_retrieve.models import Problem
from xinxingshe_auto_retrieve.pipeline import _load_cache, _save_cache


class TestStatementCacheMerge(unittest.TestCase):
    def setUp(self):
        self.dir = Path.cwd() / ".cache" / "tests" / uuid.uuid4().hex
        self.path = self.dir / "homework.json"
        self.dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_subset_run_keeps_other_entries(self):
        problems = [
            Problem(pid="P1", title="题 1", url="u1", statement="S1"),
            Problem(pid="P2", title="题 2", url="u2", statement="S2"),
        ]
        _save_cache(self.path, problems, {})
        self.assertEqual(set(_load_cache(self.path)), {"P1", "P2"})

        # 只跑 P1（模拟 --only / --max-problems），不能把 P2 冲掉。
        _save_cache(self.path, [problems[0]], {"P1": "S1"})
        cache = _load_cache(self.path)
        self.assertEqual(set(cache), {"P1", "P2"})
        self.assertEqual(cache["P2"], "S2")

    def test_failed_refresh_keeps_old_statement(self):
        problem = Problem(pid="P1", title="题 1", url="u1", statement="OLD")
        _save_cache(self.path, [problem], {})
        # 抓取失败时 statement 为空，应保留旧题面而不是写空。
        failed = Problem(pid="P1", title="题 1", url="u1", statement="")
        _save_cache(self.path, [failed], {"P1": "OLD"})
        self.assertEqual(_load_cache(self.path)["P1"], "OLD")


if __name__ == "__main__":
    unittest.main()
