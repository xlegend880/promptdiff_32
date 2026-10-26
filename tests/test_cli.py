from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from promptdiff.cli import EXIT_ERROR, EXIT_OK, EXIT_REGRESSION, main

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


class CliTest(unittest.TestCase):
    def _quiet_main(self, argv):
        """静默执行并把 stdout + stderr 合并返回，方便断言提示文案。"""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue() + err.getvalue()

    def test_validate_ok(self):
        code, out = self._quiet_main(["validate", "--suite", str(EXAMPLES / "cases.jsonl")])
        self.assertEqual(code, EXIT_OK)
        self.assertIn("8 条用例", out)

    def test_validate_bad_suite_returns_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.jsonl"
            path.write_text('{"id": "a"}\n', encoding="utf-8")
            code, out = self._quiet_main(["validate", "--suite", str(path)])
        self.assertEqual(code, EXIT_ERROR)
        self.assertIn("错误", out)

    def test_run_writes_json_and_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_json = Path(tmp) / "run.json"
            report = Path(tmp) / "report.md"
            code, _ = self._quiet_main(
                [
                    "run",
                    "--suite",
                    str(EXAMPLES / "cases.jsonl"),
                    "--provider",
                    "mock",
                    "--out",
                    str(out_json),
                    "--report",
                    str(report),
                    "--quiet",
                ]
            )
            self.assertEqual(code, EXIT_OK)
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            self.assertEqual(payload["summary"]["score"], 1.0)
            self.assertIn("# promptdiff 运行报告", report.read_text(encoding="utf-8"))

    def test_fail_on_regression_returns_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            baseline = Path(tmp) / "baseline.json"
            self._quiet_main(
                [
                    "run",
                    "--suite",
                    str(EXAMPLES / "cases.jsonl"),
                    "--provider",
                    "mock",
                    "--mock-variant",
                    "v1",
                    "--out",
                    str(baseline),
                    "--quiet",
                ]
            )
            code, out = self._quiet_main(
                [
                    "run",
                    "--suite",
                    str(EXAMPLES / "cases.jsonl"),
                    "--provider",
                    "mock",
                    "--mock-variant",
                    "v2",
                    "--baseline",
                    str(baseline),
                    "--fail-on-regression",
                    "--quiet",
                ]
            )
        self.assertEqual(code, EXIT_REGRESSION)
        self.assertIn("回归", out)

    def test_without_fail_flag_regression_returns_0(self):
        with tempfile.TemporaryDirectory() as tmp:
            baseline = Path(tmp) / "baseline.json"
            self._quiet_main(
                [
                    "run",
                    "--suite",
                    str(EXAMPLES / "cases.jsonl"),
                    "--provider",
                    "mock",
                    "--out",
                    str(baseline),
                    "--quiet",
                ]
            )
            code, _ = self._quiet_main(
                [
                    "run",
                    "--suite",
                    str(EXAMPLES / "cases.jsonl"),
                    "--provider",
                    "mock",
                    "--mock-variant",
                    "v2",
                    "--baseline",
                    str(baseline),
                    "--quiet",
                ]
            )
        self.assertEqual(code, EXIT_OK)

    def test_compare_prints_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            baseline = Path(tmp) / "b.json"
            current = Path(tmp) / "c.json"
            for variant, target in (("v1", baseline), ("v2", current)):
                self._quiet_main(
                    [
                        "run",
                        "--suite",
                        str(EXAMPLES / "cases.jsonl"),
                        "--provider",
                        "mock",
                        "--mock-variant",
                        variant,
                        "--out",
                        str(target),
                        "--quiet",
                    ]
                )
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = main(["compare", "--baseline", str(baseline), "--current", str(current)])
        self.assertEqual(code, EXIT_OK)
        self.assertIn("回归", buf.getvalue())

    def test_missing_baseline_returns_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out = self._quiet_main(
                [
                    "run",
                    "--suite",
                    str(EXAMPLES / "cases.jsonl"),
                    "--provider",
                    "mock",
                    "--baseline",
                    str(Path(tmp) / "nope.json"),
                    "--quiet",
                ]
            )
        self.assertEqual(code, EXIT_ERROR)
        self.assertIn("不存在", out)


if __name__ == "__main__":
    unittest.main()
