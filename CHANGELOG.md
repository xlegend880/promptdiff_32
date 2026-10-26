# 变更日志

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 与 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### 新增

- `--only-tags`：按 `tags` 筛选要执行的用例（多标签取并集），`run` 与 `validate` 均支持。过滤后为空会报错退出，避免「零用例满分」的假绿灯。

### 计划中

- 并发执行（`--concurrency`）
- 多模型 A/B 交叉对比
- `--update-baseline` 交互式基线更新

## [0.1.0] - 2026-10-26

首个可用版本。

### 新增

- 用例集加载：支持 JSONL 与 JSON，错误提示带行号，检测重复 `id` 与未填充占位符。
- 三类断言：`expect_contains`、`expect_not_contains`、`max_latency_ms`，外加恒开的 `non_empty`。
- 加权得分：用例级 `weight`，输出 0~1 的加权通过率。
- 基线对比：产出 `regression` / `fix` / `stable_pass` / `stable_fail` / `drift` / `new` / `removed` 七类变化。
- 漂移检测：断言仍通过但输出相似度低于阈值时告警，不阻断。
- 两个提供方：`MockProvider`（确定性、离线、免费）与 `OpenAICompatibleProvider`（任何兼容 `/chat/completions` 的端点）。
- Markdown 报告：结论先行，含用例明细表与失败详情原文。
- CLI 三个子命令：`run` / `compare` / `validate`，退出码 0/1/2 可直接用于 CI 卡点。
- 错误隔离：单条用例失败不中断整轮，记为 `error` 并在对比时按回归处理。
- 离线演示脚本 `scripts/demo.sh`，用 v1/v2 两个 mock 变体演示「回归被检出」的完整链路。
- 50 个单元测试，覆盖到 CLI 退出码。

### 设计决策

- 断言匹配忽略大小写与全部空白，但保留标点——承诺口径的差异往往就藏在这些细节里。
- 相似度用 `difflib.SequenceMatcher`（`autojunk=False`）而非向量模型，换取确定性与可解释性。
- 零运行时第三方依赖，保证三年后仍能跑起来。

[Unreleased]: https://github.com/xlegend880/promptdiff_32/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/xlegend880/promptdiff_32/releases/tag/v0.1.0
