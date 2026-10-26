"""断言与相似度计算。

这里刻意不引入任何向量模型或第三方库：
- 断言：确定性字符串匹配，结论可解释、可复现；
- 相似度：difflib 序列匹配，用于发现「断言仍然通过、但措辞漂移」的隐性变化。
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from .cases import Case

_WHITESPACE = re.compile(r"\s+")
_EDGE_CHARS = " \t\r\n。，、；：！？…—～·「」『』（）()[]{}<>\"'“”‘’.,;:!?-_/\\|*#`"


def normalize(text: str) -> str:
    """归一化：小写、压空白、去首尾标点。用于相似度比较。"""
    if not text:
        return ""
    collapsed = _WHITESPACE.sub(" ", text.lower()).strip()
    return collapsed.strip(_EDGE_CHARS)


def squash(text: str) -> str:
    """只压空白和小写，不删标点。"""
    if not text:
        return ""
    return _WHITESPACE.sub(" ", text.lower()).strip()


def compact(text: str) -> str:
    """去掉全部空白并小写。

    断言匹配用这个而不是 squash：中文场景里换行、缩进、全角空格
    经常是排版产物（"原路\\n退回"），按字符位置比对会误判为不通过。
    """
    if not text:
        return ""
    return _WHITESPACE.sub("", text.lower())


def similarity(left: str, right: str) -> float:
    """返回 0~1 的相似度。两边都为空视为完全一致。"""
    a, b = normalize(left), normalize(right)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    return round(matcher.ratio(), 4)


@dataclass(frozen=True)
class Assertion:
    """单条断言的结论。"""

    name: str
    ok: bool
    detail: str = ""


def check_assertions(case: Case, output: str) -> list:
    """对一次输出跑完该用例的全部断言。

    无论用例有没有写断言，都先检查输出非空——否则
    expect_not_contains 会因为「空输出里确实没有违规词」而误判为通过。
    """
    out = compact(output)
    results = [Assertion("non_empty", bool(out), "" if out else "模型输出为空")]

    for needle in case.expect_contains:
        ok = compact(needle) in out
        results.append(Assertion(f"contains:{needle}", ok, "" if ok else "输出中未出现该片段"))

    for needle in case.expect_not_contains:
        ok = compact(needle) not in out
        results.append(Assertion(f"not_contains:{needle}", ok, "" if ok else "输出中出现了禁止片段"))

    # 延迟断言依赖真实耗时，由 runner 调用 check_latency 追加
    return results


def check_latency(case: Case, latency_ms: float) -> Assertion | None:
    """延迟断言：超时即失败。"""
    if case.max_latency_ms is None:
        return None
    ok = latency_ms <= case.max_latency_ms
    detail = "" if ok else f"实测 {latency_ms:.1f}ms，上限 {case.max_latency_ms:g}ms"
    return Assertion(f"max_latency_ms:{case.max_latency_ms:g}", ok, detail)
