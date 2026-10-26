"""用例集的加载与校验。

支持两种格式：
- JSONL：一行一个用例，便于 review 时逐行 diff；
- JSON：{"cases": [...]} 或直接是数组。

所有格式错误都会带上行号，方便定位。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .errors import SuiteError

_PLACEHOLDER_OPEN = "{{"
_PLACEHOLDER_CLOSE = "}}"


@dataclass(frozen=True)
class Case:
    """一条测试用例。"""

    id: str
    prompt: str
    vars: dict = field(default_factory=dict)
    expect_contains: tuple = ()
    expect_not_contains: tuple = ()
    tags: tuple = ()
    weight: float = 1.0
    max_latency_ms: float | None = None

    def render(self) -> str:
        """把 vars 填进 prompt 里的 {{name}} 占位符。"""
        text = self.prompt
        for key, value in self.vars.items():
            text = text.replace(_PLACEHOLDER_OPEN + key + _PLACEHOLDER_CLOSE, str(value))
        return text

    def unresolved_placeholders(self) -> list:
        """返回没有被 vars 覆盖的占位符，便于提前发现拼写错误。"""
        rendered = self.render()
        found = []
        start = 0
        while True:
            left = rendered.find(_PLACEHOLDER_OPEN, start)
            if left < 0:
                break
            right = rendered.find(_PLACEHOLDER_CLOSE, left)
            if right < 0:
                break
            found.append(rendered[left + 2 : right])
            start = right + 2
        return found


def _as_str_list(value: Any, field_name: str, where: str) -> tuple:
    if value is None:
        return ()
    if isinstance(value, str):
        # 允许写单个字符串，减少手写负担
        return (value,)
    if not isinstance(value, (list, tuple)):
        raise SuiteError(f"{where} 字段 {field_name} 必须是字符串或字符串数组")
    out = []
    for item in value:
        if not isinstance(item, str):
            raise SuiteError(f"{where} 字段 {field_name} 的元素必须是字符串")
        if item:
            out.append(item)
    return tuple(out)


def case_from_dict(raw: Any, where: str = "用例") -> Case:
    """把一个 dict 解析成 Case，非法时抛 SuiteError。"""
    if not isinstance(raw, dict):
        raise SuiteError(f"{where} 必须是一个 JSON 对象，实际是 {type(raw).__name__}")

    case_id = raw.get("id")
    if not isinstance(case_id, str) or not case_id.strip():
        raise SuiteError(f"{where} 缺少非空的字符串字段 id")

    prompt = raw.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise SuiteError(f"{where}（id={case_id}）缺少非空的字符串字段 prompt")

    variables = raw.get("vars") or {}
    if not isinstance(variables, dict):
        raise SuiteError(f"{where}（id={case_id}）字段 vars 必须是对象")
    variables = {str(k): v for k, v in variables.items()}

    weight = raw.get("weight", 1.0)
    if not isinstance(weight, (int, float)) or isinstance(weight, bool) or weight <= 0:
        raise SuiteError(f"{where}（id={case_id}）字段 weight 必须是正数")

    max_latency = raw.get("max_latency_ms")
    if max_latency is not None and (
        not isinstance(max_latency, (int, float)) or isinstance(max_latency, bool) or max_latency <= 0
    ):
        raise SuiteError(f"{where}（id={case_id}）字段 max_latency_ms 必须是正数或省略")

    case = Case(
        id=case_id.strip(),
        prompt=prompt,
        vars=variables,
        expect_contains=_as_str_list(raw.get("expect_contains"), "expect_contains", f"{where}（id={case_id}）"),
        expect_not_contains=_as_str_list(
            raw.get("expect_not_contains"), "expect_not_contains", f"{where}（id={case_id}）"
        ),
        tags=_as_str_list(raw.get("tags"), "tags", f"{where}（id={case_id}）"),
        weight=float(weight),
        max_latency_ms=float(max_latency) if max_latency is not None else None,
    )

    leftovers = case.unresolved_placeholders()
    if leftovers:
        raise SuiteError(
            f"{where}（id={case_id}）存在未填充的占位符: {', '.join(sorted(set(leftovers)))}"
        )
    return case


def load_suite(path: str | Path) -> list:
    """按扩展名加载用例集，返回 Case 列表。"""
    p = Path(path)
    if not p.exists():
        raise SuiteError(f"用例集文件不存在: {p}")
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as exc:
        raise SuiteError(f"读取用例集失败: {exc}") from exc

    raw_items: list = []
    if p.suffix.lower() == ".jsonl":
        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            try:
                raw_items.append((json.loads(stripped), f"第 {lineno} 行"))
            except json.JSONDecodeError as exc:
                raise SuiteError(f"第 {lineno} 行不是合法 JSON: {exc.msg}") from exc
    else:
        try:
            payload = json.loads(text) if text.strip() else None
        except json.JSONDecodeError as exc:
            raise SuiteError(f"用例集不是合法 JSON: {exc.msg}") from exc
        if isinstance(payload, dict):
            items = payload.get("cases")
            if not isinstance(items, list):
                raise SuiteError("JSON 用例集需要形如 {\"cases\": [...]}")
        elif isinstance(payload, list):
            items = payload
        else:
            raise SuiteError("JSON 用例集必须是对象或数组")
        raw_items = [(item, f"第 {index + 1} 个用例") for index, item in enumerate(items)]

    if not raw_items:
        raise SuiteError(f"用例集为空: {p}")

    cases = [case_from_dict(item, where) for item, where in raw_items]
    _check_duplicate_ids(cases)
    return cases


def _check_duplicate_ids(cases: Iterable[Case]) -> None:
    seen = set()
    for case in cases:
        if case.id in seen:
            raise SuiteError(f"用例 id 重复: {case.id}")
        seen.add(case.id)


def filter_by_tags(cases: list, tags: Iterable[str]) -> list:
    """按标签取交集筛选用例。

    过滤后为空会报错而不是返回空列表：一次「什么都没跑」的运行
    在 CI 里会以满分通过，这是最危险的假绿灯。
    """
    wanted = {tag.strip() for tag in tags if tag and tag.strip()}
    if not wanted:
        return list(cases)
    selected = [case for case in cases if wanted & set(case.tags)]
    if not selected:
        raise SuiteError(f"按标签 {', '.join(sorted(wanted))} 过滤后没有任何用例")
    return selected
