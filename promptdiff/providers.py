"""模型提供方适配层。

只依赖标准库：
- MockProvider：确定性假模型，用于测试与离线演示，不产生任何费用；
- OpenAICompatibleProvider：任何兼容 /chat/completions 协议的服务都能接
  （DeepSeek、Moonshot、通义、vLLM、Ollama 的 OpenAI 兼容端点等）。
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from .errors import ProviderError


@dataclass(frozen=True)
class Completion:
    """一次模型调用的结果与元信息。"""

    text: str
    model: str
    latency_ms: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0


class Provider:
    """提供方接口。实现方只需要提供 name / model / complete。"""

    name = "base"
    model = "base"

    def complete(self, prompt: str) -> Completion:  # pragma: no cover - 抽象方法
        raise NotImplementedError


# 关键词 -> 回答模板。顺序敏感，先命中先返回。
_MOCK_ANSWERS = (
    (("退款", "退货"), "退款将在 3-5 个工作日内原路退回，具体到账时间以发卡银行为准。"),
    (("发票", "开票"), "电子发票会在付款成功后 24 小时内发送到你注册的邮箱，也可以在小程序「我的-发票」里自行下载。"),
    (("密码", "登录"), "请在登录页点击「忘记密码」，用绑定手机号接收验证码后重置密码。"),
    (("发货", "物流"), "订单发货后可在「我的订单」查看物流单号，一般 48 小时内揽收。"),
    (("人工", "客服"), "已为你转接人工客服，当前排队 2 位，请稍候。"),
)

_MOCK_FALLBACK = "已收到你的问题，我会基于知识库给出可执行的下一步操作建议。"

# v2 变体用来模拟一次真实的「提示词改动导致回归」：把承诺性的量化表述模糊化。
_DEGRADE_RULES = (
    ("3-5 个工作日", "若干工作日"),
    ("24 小时", "1 个工作日"),
    ("48 小时", "数天"),
)


class MockProvider(Provider):
    """确定性假模型。

    同一个 prompt 永远得到同一个输出，因此可以直接写进断言。
    variant="v2" 会按 _DEGRADE_RULES 降级文案，用来演示回归检测。
    """

    name = "mock"

    def __init__(self, variant: str = "v1", model: str = "mock-echo-1") -> None:
        if variant not in ("v1", "v2"):
            raise ProviderError(f"未知的 mock 变体: {variant}（可选 v1 / v2）")
        self.variant = variant
        self.model = model

    def _answer(self, prompt: str) -> str:
        lowered = prompt.lower()
        for keywords, answer in _MOCK_ANSWERS:
            if any(keyword in lowered for keyword in keywords):
                return answer
        return _MOCK_FALLBACK

    def _degrade(self, text: str) -> str:
        for old, new in _DEGRADE_RULES:
            text = text.replace(old, new)
        return text

    def _latency(self, prompt: str) -> float:
        # 用哈希造一个 80~240ms 的稳定延迟，便于报告里有可信的对比数字
        digest = hashlib.sha256(prompt.encode("utf-8")).digest()
        return 80.0 + (digest[0] / 255.0) * 160.0

    def complete(self, prompt: str) -> Completion:
        text = self._answer(prompt)
        if self.variant == "v2":
            text = self._degrade(text)
        return Completion(
            text=text,
            model=self.model,
            latency_ms=round(self._latency(prompt), 1),
            tokens_in=max(1, len(prompt) // 2),
            tokens_out=max(1, len(text) // 2),
            cost_usd=0.0,
        )


class OpenAICompatibleProvider(Provider):
    """调用任意 OpenAI 兼容的 /chat/completions 端点。"""

    name = "openai"

    def __init__(
        self,
        model: str = "deepseek-chat",
        base_url: str = "https://api.deepseek.com",
        api_key: str | None = None,
        api_key_env: str = "DEEPSEEK_API_KEY",
        timeout: float = 60.0,
        temperature: float = 0.0,
    ) -> None:
        key = api_key or os.environ.get(api_key_env, "")
        if not key:
            raise ProviderError(f"未找到 API key，请设置环境变量 {api_key_env} 或显式传入 --api-key")
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._api_key = key
        self.timeout = timeout
        self.temperature = temperature

    def complete(self, prompt: str) -> Completion:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
            "stream": False,
        }
        request = urllib.request.Request(
            url=f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
            method="POST",
        )

        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            snippet = exc.read()[:300].decode("utf-8", "replace")
            raise ProviderError(f"HTTP {exc.code} 调用失败: {snippet}") from exc
        except urllib.error.URLError as exc:
            raise ProviderError(f"网络错误: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise ProviderError(f"响应不是合法 JSON: {exc.msg}") from exc
        latency_ms = (time.perf_counter() - started) * 1000.0

        try:
            text = body["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("响应结构不符合 /chat/completions 协议") from exc

        usage = body.get("usage") or {}
        return Completion(
            text=text,
            model=body.get("model") or self.model,
            latency_ms=round(latency_ms, 1),
            tokens_in=int(usage.get("prompt_tokens") or 0),
            tokens_out=int(usage.get("completion_tokens") or 0),
            cost_usd=0.0,
        )


def get_provider(kind: str, **kwargs) -> Provider:
    """工厂方法，CLI 与测试共用。"""
    normalized = (kind or "").strip().lower()
    if normalized == "mock":
        return MockProvider(variant=kwargs.get("variant") or "v1")
    if normalized in ("openai", "openai-compatible"):
        return OpenAICompatibleProvider(
            model=kwargs.get("model") or "deepseek-chat",
            base_url=kwargs.get("base_url") or "https://api.deepseek.com",
            api_key=kwargs.get("api_key"),
            api_key_env=kwargs.get("api_key_env") or "DEEPSEEK_API_KEY",
            timeout=float(kwargs.get("timeout") or 60.0),
            temperature=float(kwargs.get("temperature") or 0.0),
        )
    raise ProviderError(f"未知的提供方: {kind}（可选 mock / openai）")
