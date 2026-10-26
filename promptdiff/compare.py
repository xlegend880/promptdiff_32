"""基线对比：判断一次运行相对上一次是「变好」还是「回归」。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .errors import BaselineError
from .metrics import similarity
from .runner import STATUS_ERROR, STATUS_PASS

CHANGE_REGRESSION = "regression"
CHANGE_FIX = "fix"
CHANGE_STABLE_PASS = "stable_pass"
CHANGE_STABLE_FAIL = "stable_fail"
CHANGE_DRIFT = "drift"
CHANGE_NEW = "new"
CHANGE_REMOVED = "removed"


@dataclass
class CaseDiff:
    """单条用例在两个版本之间的差异。"""

    id: str
    change: str
    baseline_status: str
    current_status: str
    similarity: float
    detail: str = ""


@dataclass
class RunDiff:
    """两次运行的整体差异。"""

    baseline_score: float
    current_score: float
    similarity_threshold: float
    cases: list = field(default_factory=list)

    @property
    def score_delta(self) -> float:
        return round(self.current_score - self.baseline_score, 4)

    def _by_change(self, change: str) -> list:
        return [case for case in self.cases if case.change == change]

    @property
    def regressions(self) -> list:
        return self._by_change(CHANGE_REGRESSION)

    @property
    def fixes(self) -> list:
        return self._by_change(CHANGE_FIX)

    @property
    def drifts(self) -> list:
        return self._by_change(CHANGE_DRIFT)

    @property
    def additions(self) -> list:
        return self._by_change(CHANGE_NEW)

    @property
    def removals(self) -> list:
        return self._by_change(CHANGE_REMOVED)

    def to_dict(self) -> dict:
        return {
            "baseline_score": self.baseline_score,
            "current_score": self.current_score,
            "score_delta": self.score_delta,
            "similarity_threshold": self.similarity_threshold,
            "counts": {
                "regression": len(self.regressions),
                "fix": len(self.fixes),
                "drift": len(self.drifts),
                "new": len(self.additions),
                "removed": len(self.removals),
            },
            "cases": [
                {
                    "id": item.id,
                    "change": item.change,
                    "baseline_status": item.baseline_status,
                    "current_status": item.current_status,
                    "similarity": item.similarity,
                    "detail": item.detail,
                }
                for item in self.cases
            ],
        }


def load_run(path: str | Path) -> dict:
    """读取一次运行的 JSON 结果。"""
    p = Path(path)
    if not p.exists():
        raise BaselineError(f"结果文件不存在: {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BaselineError(f"结果文件不是合法 JSON: {exc.msg}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("cases"), list):
        raise BaselineError("结果文件缺少 cases 数组，可能不是 promptdiff 的输出")
    return data


def _index(run: dict) -> dict:
    index = {}
    for case in run.get("cases", []):
        if isinstance(case, dict) and isinstance(case.get("id"), str):
            index[case["id"]] = case
    return index


def diff_runs(baseline: dict, current: dict, similarity_threshold: float = 0.9) -> RunDiff:
    """对比两份运行结果。

    判定规则：
    - 基线通过、当前不通过 -> regression（这是唯一会让 CI 失败的类别）
    - 基线不通过、当前通过 -> fix
    - 都通过但输出相似度低于阈值 -> drift（措辞漂移，仅告警）
    - 只在一侧出现 -> new / removed
    """
    base_index = _index(baseline)
    curr_index = _index(current)
    base_score = float((baseline.get("summary") or {}).get("score") or 0.0)
    curr_score = float((current.get("summary") or {}).get("score") or 0.0)

    diffs = []
    for case_id, curr in curr_index.items():
        curr_status = str(curr.get("status", STATUS_ERROR))
        base = base_index.get(case_id)
        if base is None:
            diffs.append(CaseDiff(case_id, CHANGE_NEW, "-", curr_status, 1.0, "基线中不存在该用例"))
            continue

        base_status = str(base.get("status", STATUS_ERROR))
        sim = similarity(str(base.get("output", "")), str(curr.get("output", "")))

        if base_status == STATUS_PASS and curr_status != STATUS_PASS:
            failed = [item.get("name", "?") for item in curr.get("assertions", []) if not item.get("ok", True)]
            detail = f"失败断言: {', '.join(failed)}" if failed else curr.get("error", "")
            diffs.append(CaseDiff(case_id, CHANGE_REGRESSION, base_status, curr_status, sim, detail))
        elif base_status != STATUS_PASS and curr_status == STATUS_PASS:
            diffs.append(CaseDiff(case_id, CHANGE_FIX, base_status, curr_status, sim, "断言由失败转为通过"))
        elif base_status == STATUS_PASS and curr_status == STATUS_PASS:
            if sim < similarity_threshold:
                diffs.append(
                    CaseDiff(
                        case_id,
                        CHANGE_DRIFT,
                        base_status,
                        curr_status,
                        sim,
                        f"断言仍通过，但相似度 {sim:.2f} 低于阈值 {similarity_threshold:.2f}",
                    )
                )
            else:
                diffs.append(CaseDiff(case_id, CHANGE_STABLE_PASS, base_status, curr_status, sim))
        else:
            diffs.append(CaseDiff(case_id, CHANGE_STABLE_FAIL, base_status, curr_status, sim, "仍然失败"))

    for case_id in base_index:
        if case_id not in curr_index:
            diffs.append(CaseDiff(case_id, CHANGE_REMOVED, str(base_index[case_id].get("status", "")), "-", 0.0, "当前运行中缺少该用例"))

    diffs.sort(key=lambda item: (item.change, item.id))
    return RunDiff(
        baseline_score=base_score,
        current_score=curr_score,
        similarity_threshold=similarity_threshold,
        cases=diffs,
    )
