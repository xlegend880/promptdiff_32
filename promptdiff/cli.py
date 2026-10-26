"""命令行入口。

退出码约定（方便 CI 判断）：
- 0：运行成功，且没有回归；
- 1：检测到回归（仅在传入 --fail-on-regression 时）；
- 2：用例集/提供方/基线文件等可预期错误。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .cases import filter_by_tags, load_suite
from .compare import diff_runs, load_run
from .errors import BaselineError, PromptDiffError, ProviderError, SuiteError
from .providers import get_provider
from .report import render_diff_markdown, render_run_markdown, write_text
from .runner import run_suite

EXIT_OK = 0
EXIT_REGRESSION = 1
EXIT_ERROR = 2

MAX_CONCURRENCY = 32


def _positive_int(value: str) -> int:
    """argparse 类型：必须是正整数。"""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError(f"需要正整数，收到 {value!r}") from None
    if parsed < 1:
        raise argparse.ArgumentTypeError(f"需要正整数，收到 {value!r}")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="promptdiff",
        description="面向 LLM 应用的提示词回归测试工具：跑用例、存基线、比差异。",
    )
    parser.add_argument("--version", action="version", version=f"promptdiff_32 {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="执行一次用例集")
    run_parser.add_argument("--suite", required=True, help="用例集路径（.jsonl 或 .json）")
    run_parser.add_argument("--provider", default="mock", help="提供方：mock / openai")
    run_parser.add_argument("--model", default=None, help="模型名（openai 提供方必填）")
    run_parser.add_argument("--base-url", default=None, help="OpenAI 兼容端点，默认 https://api.deepseek.com")
    run_parser.add_argument("--api-key-env", default="DEEPSEEK_API_KEY", help="读取 API key 的环境变量名")
    run_parser.add_argument("--mock-variant", default="v1", choices=["v1", "v2"], help="mock 提供方的变体")
    run_parser.add_argument("--retries", type=int, default=0, help="单条用例失败重试次数")
    run_parser.add_argument(
        "--concurrency",
        type=_positive_int,
        default=1,
        help=f"并发度，默认 1（串行）。上限 {MAX_CONCURRENCY}，结果顺序始终与用例集一致",
    )
    run_parser.add_argument("--only-tags", default=None, help="只跑包含指定标签的用例，逗号分隔，如 售后,财务")
    run_parser.add_argument("--out", default=None, help="结果 JSON 输出路径")
    run_parser.add_argument("--report", default=None, help="Markdown 报告输出路径")
    run_parser.add_argument("--baseline", default=None, help="基线结果 JSON 路径")
    run_parser.add_argument("--sim-threshold", type=float, default=0.9, help="相似度告警阈值")
    run_parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="检测到回归时以退出码 1 结束（用于 CI 卡点）",
    )
    run_parser.add_argument("--quiet", action="store_true", help="不把报告打印到 stdout")
    run_parser.set_defaults(func=cmd_run)

    compare_parser = subparsers.add_parser("compare", help="对比两份已有结果")
    compare_parser.add_argument("--baseline", required=True, help="基线结果 JSON")
    compare_parser.add_argument("--current", required=True, help="当前结果 JSON")
    compare_parser.add_argument("--sim-threshold", type=float, default=0.9)
    compare_parser.add_argument("--report", default=None, help="Markdown 报告输出路径")
    compare_parser.set_defaults(func=cmd_compare)

    validate_parser = subparsers.add_parser("validate", help="只校验用例集，不调用模型")
    validate_parser.add_argument("--suite", required=True)
    validate_parser.add_argument("--only-tags", default=None, help="只统计包含指定标签的用例，逗号分隔")
    validate_parser.set_defaults(func=cmd_validate)

    return parser


def cmd_run(args: argparse.Namespace) -> int:
    cases = load_suite(args.suite)
    if args.only_tags:
        cases = filter_by_tags(cases, args.only_tags.split(","))
    provider = get_provider(
        args.provider,
        variant=args.mock_variant,
        model=args.model,
        base_url=args.base_url,
        api_key_env=args.api_key_env,
    )
    result = run_suite(
        cases,
        provider,
        suite_label=args.suite,
        retries=args.retries,
        concurrency=min(args.concurrency, MAX_CONCURRENCY),
    )
    if args.concurrency > MAX_CONCURRENCY:
        print(
            f"[promptdiff] 并发度 {args.concurrency} 超过上限，已按 {MAX_CONCURRENCY} 执行",
            file=sys.stderr,
        )
    payload = result.to_dict()

    if args.out:
        write_text(args.out, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    diff_payload = None
    diff = None
    if args.baseline:
        diff = diff_runs(load_run(args.baseline), payload, similarity_threshold=args.sim_threshold)
        diff_payload = diff.to_dict()

    markdown = render_run_markdown(payload, diff_payload)
    if args.report:
        write_text(args.report, markdown)
    if not args.quiet:
        print(markdown)

    print(
        f"[promptdiff] {result.passed}/{result.total} 通过，加权得分 {result.score:.4f}",
        file=sys.stderr,
    )
    if diff is not None and diff.regressions:
        print(
            f"[promptdiff] 检测到 {len(diff.regressions)} 条回归: "
            + ", ".join(item.id for item in diff.regressions),
            file=sys.stderr,
        )
        if args.fail_on_regression:
            return EXIT_REGRESSION
    return EXIT_OK


def cmd_compare(args: argparse.Namespace) -> int:
    diff = diff_runs(load_run(args.baseline), load_run(args.current), similarity_threshold=args.sim_threshold)
    markdown = "# promptdiff 基线对比\n\n" + render_diff_markdown(diff.to_dict())
    if args.report:
        write_text(args.report, markdown)
        print(f"[promptdiff] 报告已写入 {args.report}", file=sys.stderr)
    else:
        print(markdown)
    return EXIT_OK


def cmd_validate(args: argparse.Namespace) -> int:
    cases = load_suite(args.suite)
    if args.only_tags:
        cases = filter_by_tags(cases, args.only_tags.split(","))
    print(f"[promptdiff] 用例集合法，共 {len(cases)} 条用例")
    return EXIT_OK


def main(argv: list | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (SuiteError, ProviderError, BaselineError) as exc:
        print(f"[promptdiff] 错误: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except (PromptDiffError, OSError) as exc:
        print(f"[promptdiff] 错误: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
