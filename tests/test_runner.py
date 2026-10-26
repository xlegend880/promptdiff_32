from __future__ import annotations

import unittest
from pathlib import Path

from promptdiff.cases import Case, load_suite
from promptdiff.errors import ProviderError
from promptdiff.providers import Completion, MockProvider, Provider, get_provider
from promptdiff.runner import STATUS_ERROR, STATUS_PASS, run_suite

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


class _FlakyProvider(Provider):
    """前 N 次调用抛错，用来验证重试与错误隔离。"""

    name = "flaky"
    model = "flaky-1"

    def __init__(self, fail_times: int) -> None:
        self.fail_times = fail_times
        self.calls = 0

    def complete(self, prompt: str) -> Completion:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise ProviderError("模拟接口超时")
        return Completion(text="退款原路退回", model=self.model, latency_ms=1.0)


class MockProviderTest(unittest.TestCase):
    def test_deterministic(self):
        provider = MockProvider()
        first = provider.complete("退款多久到账").text
        second = provider.complete("退款多久到账").text
        self.assertEqual(first, second)

    def test_keyword_routing(self):
        self.assertIn("原路退回", MockProvider().complete("退款多久到账").text)
        self.assertIn("发票", MockProvider().complete("发票怎么开").text)

    def test_fallback_for_unknown_topic(self):
        self.assertIn("下一步操作建议", MockProvider().complete("今天天气如何").text)

    def test_v2_degrades_quantified_commitments(self):
        v2 = MockProvider(variant="v2").complete("退款多久到账").text
        self.assertNotIn("3-5 个工作日", v2)

    def test_unknown_variant_rejected(self):
        with self.assertRaises(ProviderError):
            MockProvider(variant="v9")

    def test_factory(self):
        self.assertIsInstance(get_provider("mock"), MockProvider)
        with self.assertRaises(ProviderError):
            get_provider("nope")


class RunSuiteTest(unittest.TestCase):
    def test_v1_passes_all_example_cases(self):
        cases = load_suite(EXAMPLES / "cases.jsonl")
        result = run_suite(cases, MockProvider(variant="v1"))
        self.assertEqual(result.total, len(cases))
        self.assertEqual(result.failed, 0)
        self.assertEqual(result.errored, 0)
        self.assertEqual(result.score, 1.0)

    def test_v2_triggers_failures(self):
        cases = load_suite(EXAMPLES / "cases.jsonl")
        result = run_suite(cases, MockProvider(variant="v2"))
        self.assertGreater(result.failed, 0)
        self.assertLess(result.score, 1.0)
        self.assertIn("refund-quantified", [case.id for case in result.cases if case.status != STATUS_PASS])

    def test_error_does_not_abort_run(self):
        cases = [Case(id="a", prompt="退款", expect_contains=["原路退回"]), Case(id="b", prompt="发票")]
        provider = _FlakyProvider(fail_times=1)
        result = run_suite(cases, provider)
        self.assertEqual(result.total, 2)
        self.assertEqual(result.errored, 1)
        self.assertEqual(result.cases[1].status, STATUS_PASS)

    def test_retries_recover(self):
        cases = [Case(id="a", prompt="退款")]
        result = run_suite(cases, _FlakyProvider(fail_times=1), retries=1)
        self.assertEqual(result.errored, 0)

    def test_to_dict_shape(self):
        cases = [Case(id="a", prompt="退款", expect_contains=["原路退回"])]
        payload = run_suite(cases, MockProvider()).to_dict()
        self.assertIn("summary", payload)
        self.assertEqual(payload["summary"]["total"], 1)
        self.assertIsInstance(payload["cases"][0]["assertions"], list)
        self.assertEqual(payload["cases"][0]["assertions"][0]["name"], "non_empty")


if __name__ == "__main__":
    unittest.main()
