"""用例执行器：把「用例集 + 提供方」跑成一份结构化结果。"""

from __future__ import annotations

import datetime as _dt
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field

from . import __version__
from .cases import Case
from .errors import ProviderError
from .metrics import Assertion, check_assertions, check_latency
from .providers import Provider

STATUS_PASS = "pass"
STATUS_FAIL = "fail"
STATUS_ERROR = "error"


@dataclass
class CaseResult:
    """单条用例的执行结果。"""

    id: str
    status: str
    prompt: str
    output: str
    model: str
    latency_ms: float
    tokens_in: int
    tokens_out: int
    cost_usd: float
    weight: float
    assertions: list = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict:
        data = asdict(self)
        data["assertions"] = [asdict(item) for item in self.assertions]
        return data


@dataclass
class RunResult:
    """一次完整运行的聚合结果。"""

    provider: str
    model: str
    suite: str
    started_at: str
    duration_ms: float
    cases: list
    concurrency: int = 1
    tool_version: str = __version__

    @property
    def total(self) -> int:
        return len(self.cases)

    @property
    def passed(self) -> int:
        return sum(1 for case in self.cases if case.status == STATUS_PASS)

    @property
    def failed(self) -> int:
        return sum(1 for case in self.cases if case.status == STATUS_FAIL)

    @property
    def errored(self) -> int:
        return sum(1 for case in self.cases if case.status == STATUS_ERROR)

    @property
    def score(self) -> float:
        """加权通过率，权重来自用例的 weight 字段。"""
        total_weight = sum(case.weight for case in self.cases)
        if total_weight <= 0:
            return 0.0
        gained = sum(case.weight for case in self.cases if case.status == STATUS_PASS)
        return round(gained / total_weight, 4)

    @property
    def total_cost_usd(self) -> float:
        return round(sum(case.cost_usd for case in self.cases), 6)

    @property
    def avg_latency_ms(self) -> float:
        if not self.cases:
            return 0.0
        return round(sum(case.latency_ms for case in self.cases) / len(self.cases), 1)

    def to_dict(self) -> dict:
        return {
            "tool_version": self.tool_version,
            "provider": self.provider,
            "model": self.model,
            "suite": self.suite,
            "started_at": self.started_at,
            "duration_ms": round(self.duration_ms, 1),
            "concurrency": self.concurrency,
            "summary": {
                "total": self.total,
                "passed": self.passed,
                "failed": self.failed,
                "errored": self.errored,
                "score": self.score,
                "avg_latency_ms": self.avg_latency_ms,
                "total_cost_usd": self.total_cost_usd,
            },
            "cases": [case.to_dict() for case in self.cases],
        }


def run_suite(
    cases: list,
    provider: Provider,
    suite_label: str = "<memory>",
    retries: int = 0,
    concurrency: int = 1,
    on_case=None,
) -> RunResult:
    """逐条执行用例。

    单条用例抛错不会中断整轮运行，而是记为 error 状态——
    回归测试最怕的就是「一条网络抖动导致整份报告没有产出」。

    concurrency > 1 时用线程池并发执行，但**结果顺序永远与用例集一致**。
    """
    started_at = _dt.datetime.now(_dt.timezone.utc).astimezone().isoformat(timespec="seconds")
    started = time.perf_counter()

    if concurrency > 1 and len(cases) > 1:
        results = _run_concurrently(cases, provider, retries, concurrency, on_case)
    else:
        results = []
        for case in cases:
            results.append(_run_one(case, provider, retries))
            if on_case is not None:
                on_case(results[-1])

    duration_ms = (time.perf_counter() - started) * 1000.0
    return RunResult(
        provider=getattr(provider, "name", "unknown"),
        model=getattr(provider, "model", "unknown"),
        suite=str(suite_label),
        started_at=started_at,
        duration_ms=duration_ms,
        cases=results,
        concurrency=max(1, concurrency),
    )


def _run_concurrently(cases: list, provider: Provider, retries: int, concurrency: int, on_case=None) -> list:
    """线程池执行，按提交顺序收集结果。

    这里刻意不用 `as_completed`：它按完成顺序产出，会让报告的行序随网络抖动变化，
    跨版本 diff 直接变成噪声。必须按 futures 列表的原始顺序取回结果。

    并发度会被裁剪到不超过用例数，避免开一堆空转线程。
    """
    workers = max(1, min(concurrency, len(cases)))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="promptdiff") as pool:
        futures = [pool.submit(_run_one, case, provider, retries) for case in cases]
        results = []
        for future in futures:
            result = future.result()
            results.append(result)
            if on_case is not None:
                on_case(result)
    return results


def _run_one(case: Case, provider: Provider, retries: int) -> CaseResult:
    prompt = case.render()
    attempt = 0
    while True:
        try:
            completion = provider.complete(prompt)
            break
        except ProviderError as exc:
            attempt += 1
            if attempt > retries:
                return CaseResult(
                    id=case.id,
                    status=STATUS_ERROR,
                    prompt=prompt,
                    output="",
                    model=getattr(provider, "model", "unknown"),
                    latency_ms=0.0,
                    tokens_in=0,
                    tokens_out=0,
                    cost_usd=0.0,
                    weight=case.weight,
                    assertions=[],
                    error=str(exc),
                )

    assertions = check_assertions(case, completion.text)
    latency_assertion = check_latency(case, completion.latency_ms)
    if latency_assertion is not None:
        assertions.append(latency_assertion)

    status = STATUS_PASS if all(item.ok for item in assertions) else STATUS_FAIL
    return CaseResult(
        id=case.id,
        status=status,
        prompt=prompt,
        output=completion.text,
        model=completion.model,
        latency_ms=completion.latency_ms,
        tokens_in=completion.tokens_in,
        tokens_out=completion.tokens_out,
        cost_usd=completion.cost_usd,
        weight=case.weight,
        assertions=assertions,
    )
