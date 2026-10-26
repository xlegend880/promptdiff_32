from __future__ import annotations

import unittest

from promptdiff.compare import (
    CHANGE_DRIFT,
    CHANGE_FIX,
    CHANGE_NEW,
    CHANGE_REGRESSION,
    CHANGE_REMOVED,
    diff_runs,
)


def _run(*cases, score=1.0):
    return {
        "summary": {"score": score},
        "cases": list(cases),
    }


def _case(case_id, status, output="ok"):
    return {
        "id": case_id,
        "status": status,
        "output": output,
        "assertions": [{"name": "contains:x", "ok": status == "pass", "detail": ""}],
    }


class DiffTest(unittest.TestCase):
    def test_regression_detected(self):
        diff = diff_runs(_run(_case("a", "pass")), _run(_case("a", "fail"), score=0.0))
        self.assertEqual(len(diff.regressions), 1)
        self.assertEqual(diff.regressions[0].id, "a")
        self.assertAlmostEqual(diff.score_delta, -1.0)

    def test_error_counts_as_regression(self):
        diff = diff_runs(_run(_case("a", "pass")), _run(_case("a", "error")))
        self.assertEqual(len(diff.regressions), 1)

    def test_fix_detected(self):
        diff = diff_runs(_run(_case("a", "fail"), score=0.0), _run(_case("a", "pass")))
        self.assertEqual(len(diff.fixes), 1)
        self.assertEqual(diff.fixes[0].change, CHANGE_FIX)

    def test_drift_when_text_changes_but_passes(self):
        baseline = _run(_case("a", "pass", "退款将在 3-5 个工作日内原路退回"))
        current = _run(_case("a", "pass", "退款会处理，请耐心等待结果"))
        diff = diff_runs(baseline, current, similarity_threshold=0.9)
        self.assertEqual(len(diff.drifts), 1)
        self.assertEqual(diff.drifts[0].change, CHANGE_DRIFT)
        self.assertEqual(diff.regressions, [])

    def test_new_and_removed(self):
        diff = diff_runs(_run(_case("old", "pass")), _run(_case("fresh", "pass")))
        self.assertEqual([item.id for item in diff.additions], ["fresh"])
        self.assertEqual([item.id for item in diff.removals], ["old"])
        self.assertEqual(diff.additions[0].change, CHANGE_NEW)
        self.assertEqual(diff.removals[0].change, CHANGE_REMOVED)

    def test_identical_runs_have_no_changes(self):
        run = _run(_case("a", "pass"), _case("b", "fail"))
        diff = diff_runs(run, run)
        self.assertEqual(diff.regressions, [])
        self.assertEqual(diff.fixes, [])
        self.assertEqual(diff.score_delta, 0.0)

    def test_to_dict_counts(self):
        diff = diff_runs(_run(_case("a", "pass"), _case("b", "pass")), _run(_case("a", "fail"), _case("b", "pass")))
        payload = diff.to_dict()
        self.assertEqual(payload["counts"]["regression"], 1)
        self.assertEqual(len(payload["cases"]), 2)


if __name__ == "__main__":
    unittest.main()
