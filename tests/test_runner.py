from __future__ import annotations

import threading
import time
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


class _TrackingProvider(Provider):
    """记录同时在飞的调用数，用来证明并发真的重叠了。"""

    name = "tracking"
    model = "tracking-1"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active = 0
        self.max_active = 0

    def complete(self, prompt: str) -> Completion:
        with self._lock:
            self._active += 1
            self.max_active = max(self.max_active, self._active)
        time.sleep(0.02)
        with self._lock:
            self._active -= 1
        return Completion(text="ok", model=self.model, latency_ms=20.0)


class ConcurrencyTest(unittest.TestCase):
    def test_order_matches_input_under_concurrency(self):
        cases = [Case(id=f"c{index:02d}", prompt=f"退款 {index}") for index in range(12)]
        serial = run_suite(cases, MockProvider(), concurrency=1)
        parallel = run_suite(cases, MockProvider(), concurrency=4)
        self.assertEqual([item.id for item in parallel.cases], [case.id for case in cases])
        self.assertEqual([item.output for item in parallel.cases], [item.output for item in serial.cases])

    def test_score_is_identical_to_serial(self):
        cases = load_suite(EXAMPLES / "cases.jsonl")
        serial = run_suite(cases, MockProvider(variant="v2"), concurrency=1)
        parallel = run_suite(cases, MockProvider(variant="v2"), concurrency=4)
        self.assertEqual(serial.score, parallel.score)
        self.assertEqual(serial.passed, parallel.passed)
        self.assertEqual([item.status for item in serial.cases], [item.status for item in parallel.cases])

    def test_calls_actually_overlap(self):
        provider = _TrackingProvider()
        cases = [Case(id=f"c{index}", prompt="x") for index in range(8)]
        run_suite(cases, provider, concurrency=4)
        self.assertGreater(provider.max_active, 1)
        self.assertLessEqual(provider.max_active, 4)

    def test_workers_clamped_to_case_count(self):
        provider = _TrackingProvider()
        run_suite([Case(id="only", prompt="x")], provider, concurrency=16)
        self.assertEqual(provider.max_active, 1)

    def test_concurrency_recorded_in_result(self):
        payload = run_suite([Case(id="a", prompt="退款")], MockProvider(), concurrency=4).to_dict()
        self.assertEqual(payload["concurrency"], 4)


if __name__ == "__main__":
    unittest.main()
