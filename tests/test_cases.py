from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from promptdiff.cases import case_from_dict, filter_by_tags, load_suite
from promptdiff.errors import SuiteError

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


class LoadSuiteTest(unittest.TestCase):
    def test_loads_jsonl_example(self):
        cases = load_suite(EXAMPLES / "cases.jsonl")
        self.assertEqual(len(cases), 8)
        self.assertEqual(cases[0].id, "refund-sla")
        self.assertEqual(cases[0].weight, 2.0)

    def test_loads_json_example(self):
        cases = load_suite(EXAMPLES / "suite.json")
        self.assertEqual([case.id for case in cases], ["json-refund", "json-password"])

    def test_render_replaces_placeholders(self):
        case = case_from_dict({"id": "a", "prompt": "{{product}} 的退款", "vars": {"product": "会员"}})
        self.assertEqual(case.render(), "会员 的退款")
        self.assertEqual(case.unresolved_placeholders(), [])

    def test_missing_id_raises(self):
        with self.assertRaises(SuiteError):
            case_from_dict({"prompt": "hi"})

    def test_missing_prompt_raises(self):
        with self.assertRaises(SuiteError):
            case_from_dict({"id": "a"})

    def test_bad_weight_raises(self):
        with self.assertRaises(SuiteError):
            case_from_dict({"id": "a", "prompt": "hi", "weight": 0})

    def test_regex_assertions_parsed(self):
        case = case_from_dict(
            {
                "id": "reg1",
                "prompt": "test",
                "expect_regex": r"\d+",
                "expect_not_regex": [r"error", r"fail"],
            }
        )
        self.assertEqual(case.expect_regex, (r"\d+",))
        self.assertEqual(case.expect_not_regex, (r"error", r"fail"))

    def test_invalid_regex_raises(self):
        with self.assertRaises(SuiteError) as ctx:
            case_from_dict({"id": "a", "prompt": "p", "expect_regex": "[open("})
        self.assertIn("非法正则表达式", str(ctx.exception))

        with self.assertRaises(SuiteError) as ctx:
            case_from_dict({"id": "a", "prompt": "p", "expect_not_regex": "(?P<bad"})
        self.assertIn("非法正则表达式", str(ctx.exception))

    def test_unresolved_placeholder_raises(self):
        with self.assertRaises(SuiteError) as ctx:
            case_from_dict({"id": "a", "prompt": "{{missing}} 你好"})
        self.assertIn("missing", str(ctx.exception))

    def test_duplicate_id_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dup.jsonl"
            path.write_text(
                json.dumps({"id": "a", "prompt": "1"}) + "\n" + json.dumps({"id": "a", "prompt": "2"}) + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(SuiteError) as ctx:
                load_suite(path)
            self.assertIn("重复", str(ctx.exception))

    def test_broken_jsonl_reports_line_number(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.jsonl"
            path.write_text('{"id": "a", "prompt": "1"}\n{not json}\n', encoding="utf-8")
            with self.assertRaises(SuiteError) as ctx:
                load_suite(path)
            self.assertIn("第 2 行", str(ctx.exception))

    def test_empty_suite_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "empty.jsonl"
            path.write_text("\n\n", encoding="utf-8")
            with self.assertRaises(SuiteError):
                load_suite(path)

    def test_missing_file_raises(self):
        with self.assertRaises(SuiteError):
            load_suite("/tmp/definitely-not-here-32.jsonl")


class FilterByTagsTest(unittest.TestCase):
    def setUp(self):
        self.cases = load_suite(EXAMPLES / "cases.jsonl")

    def test_filters_by_intersection(self):
        selected = filter_by_tags(self.cases, ["售后"])
        self.assertEqual({case.id for case in selected}, {"refund-sla", "refund-quantified", "refund-with-vars"})

    def test_multiple_tags_is_union(self):
        selected = filter_by_tags(self.cases, ["财务", "物流"])
        self.assertEqual({case.id for case in selected}, {"invoice-window", "shipping-query"})

    def test_empty_filter_keeps_everything(self):
        self.assertEqual(len(filter_by_tags(self.cases, [])), len(self.cases))
        self.assertEqual(len(filter_by_tags(self.cases, ["  "])), len(self.cases))

    def test_no_match_raises_instead_of_returning_empty(self):
        # 空集合会让 CI 以满分通过，必须显式报错
        with self.assertRaises(SuiteError):
            filter_by_tags(self.cases, ["不存在的标签"])


if __name__ == "__main__":
    unittest.main()
