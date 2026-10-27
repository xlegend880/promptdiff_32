# 变更日志

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 与 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### 计划中

- 正则断言超时保护（#7）
- 多模型 A/B 交叉对比
- `--update-baseline` 交互式基线更新

## [0.3.0] - 2026-10-28

### 新增

- 正则断言：`expect_regex` / `expect_not_regex`，用于约束单号、金额、日期等有固定形状的字段。由 @Nad-Am 在 #5 中实现，是项目收到的第一个外部代码贡献。
- 非法正则在校验阶段拦截，错误信息带用例 id，`promptdiff validate` 可在不调用模型的情况下先行检查。

### 文档

- README 与 `docs/usage.md` 补充正则断言的使用要点，重点是**正则按原始文本匹配、`.` 默认不跨行**，与 contains 的「压掉空白再比」语义不同（#5 评审中提出）。

## [0.2.0] - 2026-10-26

### 新增

- 并发执行：`--concurrency N`，用例级线程池，默认 1（串行），上限 32。**结果顺序始终与用例集原始顺序一致**——若按完成顺序落盘，报告 diff 会随网络抖动变化，跨版本对比直接失效。
- 结果 JSON 新增 `concurrency` 字段，便于事后判断一次运行是串行还是并发。

### 修复

- CHANGELOG 中已随 v0.1.0 发布的条目（`--only-tags`、相似度三位小数、说明列 120 字）曾被误记为 Unreleased，现归位到 0.1.0。

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
- `--only-tags`：按 `tags` 筛选要执行的用例（多标签取并集），`run` 与 `validate` 均支持。过滤后为空会报错退出，避免「零用例满分」的假绿灯。
- 差异报告的相似度列改为三位小数：阈值附近 0.89 与 0.90 在两位小数下看不出差别，无法判断是否越界。
- 差异报告的「说明」列截断宽度由 80 字放宽到 120 字：断言失败原因经常在 80 字之后才说到点上。
- 50 个单元测试，覆盖到 CLI 退出码。

### 设计决策

- 断言匹配忽略大小写与全部空白，但保留标点——承诺口径的差异往往就藏在这些细节里。
- 相似度用 `difflib.SequenceMatcher`（`autojunk=False`）而非向量模型，换取确定性与可解释性。
- 零运行时第三方依赖，保证三年后仍能跑起来。

[Unreleased]: https://github.com/xlegend880/promptdiff_32/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/xlegend880/promptdiff_32/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/xlegend880/promptdiff_32/releases/tag/v0.1.0
