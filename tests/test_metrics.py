from __future__ import annotations

import unittest

from promptdiff.cases import Case
from promptdiff.metrics import check_assertions, check_latency, normalize, similarity, squash


class NormalizeTest(unittest.TestCase):
    def test_collapses_whitespace_and_lowercases(self):
        self.assertEqual(normalize("  Hello   World \n"), "hello world")

    def test_strips_edge_punctuation(self):
        self.assertEqual(normalize("退款已完成。"), "退款已完成")

    def test_empty_input(self):
        self.assertEqual(normalize(""), "")
        self.assertEqual(normalize(None), "")

    def test_squash_keeps_punctuation(self):
        self.assertEqual(squash("A，B"), "a，b")


class SimilarityTest(unittest.TestCase):
    def test_identical_is_one(self):
        self.assertEqual(similarity("退款三天到账", "退款三天到账"), 1.0)

    def test_both_empty_is_one(self):
        self.assertEqual(similarity("", ""), 1.0)

    def test_one_empty_is_zero(self):
        self.assertEqual(similarity("abc", ""), 0.0)

    def test_symmetric(self):
        left, right = "退款将在 3-5 个工作日到账", "退款将在若干工作日到账"
        self.assertAlmostEqual(similarity(left, right), similarity(right, left))

    def test_partial_change_is_between(self):
        score = similarity("退款将在 3-5 个工作日到账", "退款将在若干工作日到账")
        self.assertGreater(score, 0.5)
        self.assertLess(score, 1.0)


class AssertionTest(unittest.TestCase):
    def _case(self, **kwargs):
        return Case(id="c1", prompt="p", **kwargs)

    def test_empty_output_always_fails(self):
        results = check_assertions(self._case(expect_not_contains=["违规"]), "")
        self.assertFalse(all(item.ok for item in results))
        self.assertEqual(results[0].name, "non_empty")

    def test_contains_matches_case_insensitively(self):
        results = check_assertions(self._case(expect_contains=["refund"]), "REFUND done")
        self.assertTrue(all(item.ok for item in results))

    def test_not_contains_detects_violation(self):
        results = check_assertions(self._case(expect_not_contains=["保证"]), "我们保证到账")
        failed = [item for item in results if not item.ok]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0].name, "not_contains:保证")

    def test_whitespace_differences_do_not_break_contains(self):
        results = check_assertions(self._case(expect_contains=["原路退回"]), "款项  将原路\n退回")
        self.assertTrue(all(item.ok for item in results))

    def test_regex_matches_pattern(self):
        results = check_assertions(self._case(expect_regex=[r"\d{3}-\d{4}"]), "订单号是 021-8888。")
        self.assertTrue(all(item.ok for item in results))

    def test_regex_fails_when_unmatched(self):
        results = check_assertions(self._case(expect_regex=[r"^\d{4}$"]), "abc")
        failed = [item for item in results if not item.ok]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0].name, r"regex:^\d{4}$")
        self.assertIn("未匹配", failed[0].detail)

    def test_not_regex_passes_when_clean(self):
        results = check_assertions(self._case(expect_not_regex=[r"1[3-9]\d{9}"]), "无手机号")
        self.assertTrue(all(item.ok for item in results))

    def test_not_regex_detects_violation(self):
        results = check_assertions(self._case(expect_not_regex=[r"1[3-9]\d{9}"]), "联系方式 13800138000")
        failed = [item for item in results if not item.ok]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0].name, r"not_regex:1[3-9]\d{9}")
        self.assertIn("匹配了禁止正则", failed[0].detail)

    def test_latency_assertion(self):
        case = self._case(max_latency_ms=100)
        self.assertTrue(check_latency(case, 99).ok)
        self.assertFalse(check_latency(case, 101).ok)
        self.assertIsNone(check_latency(self._case(), 999))


if __name__ == "__main__":
    unittest.main()
