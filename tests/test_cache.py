import json
import shutil
import time
import unittest
import uuid
from pathlib import Path

from xinxingshe_auto_retrieve.cache import ResultCache
from xinxingshe_auto_retrieve.models import Candidate


def sample_candidates() -> list[Candidate]:
    return [
        Candidate(
            title="Pudding Monsters",
            source="Codeforces",
            url="https://codeforces.com/problemset/problem/526/F",
            score=0.8244,
            group=0,
        ),
        Candidate(
            title="布丁怪兽",
            source="Luogu",
            url="https://www.luogu.com.cn/problem/P6256",
            score=0.81,
            group=0,
            is_duplicate=True,
        ),
    ]


class TestResultCache(unittest.TestCase):
    def setUp(self):
        # 放在工作区 .cache 下：系统临时目录在部分沙箱中不可写/不可清理。
        self.dir = Path.cwd() / ".cache" / "tests" / uuid.uuid4().hex
        self.dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_roundtrip(self):
        cache = ResultCache(self.dir, 14, "api-v1")
        cache.store("query", sample_candidates(), 100, 12.3)
        loaded = cache.load("query")
        self.assertIsNotNone(loaded)
        candidates, total, elapsed = loaded
        self.assertEqual(total, 100)
        self.assertAlmostEqual(elapsed, 12.3)
        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[0].title, "Pudding Monsters")
        self.assertEqual(candidates[1].source, "Luogu")
        self.assertTrue(candidates[1].is_duplicate)
        self.assertEqual(candidates[1].group, 0)

    def test_namespace_changes_key(self):
        cache = ResultCache(self.dir, 14, "api-v1")
        cache.store("query", sample_candidates(), 1, 1.0)
        other = ResultCache(self.dir, 14, "api-v2")
        self.assertIsNone(other.load("query"))

    def test_expired(self):
        cache = ResultCache(self.dir, 1.0 / 86400.0, "api-v1")  # 1 秒
        cache.store("query", sample_candidates(), 1, 1.0)
        path = cache._path("query")
        data = json.loads(path.read_text(encoding="utf-8"))
        data["created_at"] = time.time() - 10
        path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIsNone(cache.load("query"))

    def test_disabled(self):
        cache = ResultCache(self.dir, 0, "api-v1")
        self.assertFalse(cache.enabled)
        cache.store("query", sample_candidates(), 1, 1.0)
        self.assertIsNone(cache.load("query"))

    def test_bypass_read_still_writes(self):
        cache = ResultCache(self.dir, 14, "api-v1")
        cache.store("query", sample_candidates(), 1, 1.0)
        bypass = ResultCache(self.dir, 14, "api-v1", bypass_read=True)
        self.assertIsNone(bypass.load("query"))
        bypass.store("query2", sample_candidates(), 2, 2.0)
        self.assertIsNotNone(cache.load("query2"))

    def test_empty_candidates_not_stored(self):
        cache = ResultCache(self.dir, 14, "api-v1")
        cache.store("query", [], 0, 0.0)
        self.assertIsNone(cache.load("query"))


if __name__ == "__main__":
    unittest.main()
