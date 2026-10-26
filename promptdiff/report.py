"""报告渲染：把运行结果变成 Markdown。

报告是给人看的，所以刻意保留三样东西：
1. 结论先行（得分、通过数、是否回归）；
2. 失败用例的原文输出，方便直接改提示词；
3. 与基线的差异清单，方便在 PR 里说清「这次改动影响了什么」。
"""

from __future__ import annotations

from pathlib import Path

_STATUS_LABEL = {
    "pass": "PASS",
    "fail": "FAIL",
    "error": "ERROR",
}

_CHANGE_LABEL = {
    "regression": "回归",
    "fix": "修复",
    "stable_pass": "稳定通过",
    "stable_fail": "仍然失败",
    "drift": "措辞漂移",
    "new": "新增",
    "removed": "移除",
}


def _cell(text: str, limit: int = 120) -> str:
    """表格单元格转义 + 截断。"""
    flat = " ".join(str(text).split())
    if len(flat) > limit:
        flat = flat[: limit - 1] + "…"
    return flat.replace("|", "\\|")


def render_diff_markdown(diff: dict) -> str:
    """渲染基线差异区块。"""
    counts = diff.get("counts") or {}
    lines = [
        "## 与基线的差异",
        "",
        f"- 基线得分 **{diff.get('baseline_score', 0):.4f}** → 当前得分 **{diff.get('current_score', 0):.4f}**"
        f"（Δ {diff.get('score_delta', 0):+.4f}）",
        f"- 回归 {counts.get('regression', 0)} · 修复 {counts.get('fix', 0)} · "
        f"漂移 {counts.get('drift', 0)} · 新增 {counts.get('new', 0)} · 移除 {counts.get('removed', 0)}",
        f"- 相似度告警阈值：{diff.get('similarity_threshold', 0):.2f}",
        "",
        "| 用例 | 变化 | 基线 | 当前 | 相似度 | 说明 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for case in diff.get("cases", []):
        change = case.get("change", "")
        lines.append(
            "| {id} | {change} | {base} | {curr} | {sim:.2f} | {detail} |".format(
                id=_cell(case.get("id", ""), 40),
                change=_CHANGE_LABEL.get(change, change),
                base=_cell(case.get("baseline_status", "-"), 12),
                curr=_cell(case.get("current_status", "-"), 12),
                sim=float(case.get("similarity", 0.0)),
                detail=_cell(case.get("detail", ""), 80),
            )
        )
    lines.append("")
    return "\n".join(lines)


def render_run_markdown(run: dict, diff: dict | None = None) -> str:
    """渲染一份完整运行报告。"""
    summary = run.get("summary") or {}
    cases = run.get("cases", [])
    failed_cases = [case for case in cases if case.get("status") != "pass"]

    lines = [
        "# promptdiff 运行报告",
        "",
        "## 结论",
        "",
        f"- 加权得分：**{summary.get('score', 0):.4f}**"
        f"（{summary.get('passed', 0)}/{summary.get('total', 0)} 通过，"
        f"失败 {summary.get('failed', 0)}，错误 {summary.get('errored', 0)}）",
        f"- 提供方：`{run.get('provider', '')}` / 模型：`{run.get('model', '')}`",
        f"- 用例集：`{run.get('suite', '')}`",
        f"- 执行时间：{run.get('started_at', '')}，总耗时 {run.get('duration_ms', 0):.0f}ms，"
        f"平均单例延迟 {summary.get('avg_latency_ms', 0):.1f}ms",
        f"- 预估成本：${summary.get('total_cost_usd', 0):.6f}",
        "",
    ]

    if diff is not None:
        verdict = "存在回归，建议阻断合并" if (diff.get("counts") or {}).get("regression") else "无回归"
        lines.extend([f"- 基线对比结论：**{verdict}**", ""])

    lines.extend(
        [
            "## 用例明细",
            "",
            "| 用例 | 状态 | 延迟(ms) | 断言 | 输出摘要 |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for case in cases:
        assertions = case.get("assertions") or []
        passed = sum(1 for item in assertions if item.get("ok"))
        lines.append(
            "| {id} | {status} | {latency:.1f} | {passed}/{total} | {output} |".format(
                id=_cell(case.get("id", ""), 40),
                status=_STATUS_LABEL.get(case.get("status", ""), case.get("status", "")),
                latency=float(case.get("latency_ms", 0.0)),
                passed=passed,
                total=len(assertions),
                output=_cell(case.get("output", "") or case.get("error", ""), 100),
            )
        )
    lines.append("")

    if failed_cases:
        lines.extend(["## 失败详情", ""])
        for case in failed_cases:
            lines.append(f"### `{case.get('id', '')}`")
            lines.append("")
            lines.append(f"- 状态：{_STATUS_LABEL.get(case.get('status', ''), case.get('status', ''))}")
            if case.get("error"):
                lines.append(f"- 错误：{case['error']}")
            for item in case.get("assertions") or []:
                if not item.get("ok"):
                    lines.append(f"- 未通过断言 `{item.get('name', '')}`：{item.get('detail', '')}")
            lines.append(f"- 输入：{_cell(case.get('prompt', ''), 300)}")
            lines.append(f"- 输出：{_cell(case.get('output', ''), 300)}")
            lines.append("")

    if diff is not None:
        lines.append(render_diff_markdown(diff))

    lines.append("---")
    lines.append("")
    lines.append(f"由 promptdiff_32 v{run.get('tool_version', '')} 生成。")
    lines.append("")
    return "\n".join(lines)


def write_text(path: str | Path, text: str) -> Path:
    """写文件并自动建目录。"""
    p = Path(path)
    if p.parent and not p.parent.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p
