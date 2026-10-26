# 架构说明

## 一、整体结构

```
                     ┌──────────────┐
   examples/*.jsonl  │  cases.py    │  加载 / 校验 / 渲染占位符
   ─────────────────▶│  Case        │
                     └──────┬───────┘
                            │ list[Case]
                            ▼
   ┌────────────┐    ┌──────────────┐    ┌──────────────┐
   │providers.py│───▶│  runner.py   │───▶│  RunResult   │
   │ Mock /     │    │  逐条执行     │    │  cases[]     │
   │ OpenAI 兼容 │◀───│  错误隔离     │    └──────┬───────┘
   └────────────┘    └──────────────┘           │
                            ▲                    │ to_dict()
                     metrics.py                  ▼
              归一化 / 相似度 / 断言      ┌──────────────┐
                                          │  JSON 结果   │
                                          └──────┬───────┘
                                                 │
   ┌────────────┐    ┌──────────────┐           │
   │compare.py  │◀───│ 基线 JSON    │◀──────────┘
   │ 七类变化判定 │    └──────────────┘
   └──────┬─────┘
          │ RunDiff
          ▼
   ┌────────────┐
   │ report.py  │──▶ Markdown 报告（人看）
   │  cli.py    │──▶ 退出码 0/1/2（CI 看）
   └────────────┘
```

## 二、模块职责

| 模块 | 职责 | 不负责 |
| --- | --- | --- |
| `cases.py` | 把文件变成 `Case` 对象，非法输入给出带行号的错误 | 不判断用例「写得好不好」 |
| `metrics.py` | 纯函数：归一化、相似度、断言判定 | 不碰 IO，不碰网络 |
| `providers.py` | 屏蔽模型差异，统一返回 `Completion` | 不做重试（重试属于执行策略） |
| `runner.py` | 编排执行、聚合统计、错误隔离 | 不做对比，不做渲染 |
| `compare.py` | 判定两版结果之间的七类变化 | 不决定「该不该失败」，那是 CLI 的事 |
| `report.py` | 把结构化数据渲染成人能读的 Markdown | 不计算任何指标 |
| `cli.py` | 参数解析、组装调用链、映射退出码 | 不含业务逻辑 |

关键约束：**`metrics.py` 是纯函数模块**。它没有 IO、没有随机、没有全局状态，因此可以用最简单的单元测试覆盖，也保证了同一份输入在任何机器上得到同一个分数。

## 三、数据契约

### 用例（输入）

```json
{"id": "refund-sla", "prompt": "...", "vars": {}, "expect_contains": ["..."],
 "expect_not_contains": [], "tags": [], "weight": 1.0, "max_latency_ms": 300}
```

`id` 是基线对比的主键，**一旦发布就不要改**——改了等于删掉旧用例再加一条新用例，历史基线会丢失对比关系。

### 运行结果（中间产物，也是基线）

```json
{
  "tool_version": "0.1.0",
  "provider": "mock", "model": "mock-echo-1",
  "suite": "examples/cases.jsonl",
  "started_at": "2026-10-26T15:30:15+08:00",
  "duration_ms": 0.4,
  "concurrency": 1,
  "summary": {"total": 8, "passed": 6, "failed": 2, "errored": 0,
              "score": 0.7143, "avg_latency_ms": 164.9, "total_cost_usd": 0.0},
  "cases": [
    {"id": "...", "status": "pass|fail|error", "prompt": "...", "output": "...",
     "model": "...", "latency_ms": 123.4, "tokens_in": 10, "tokens_out": 20,
     "cost_usd": 0.0, "weight": 1.0,
     "assertions": [{"name": "contains:x", "ok": true, "detail": ""}],
     "error": ""}
  ]
}
```

这份 JSON 同时承担三个角色：报告的数据源、基线的载体、跨工具的交换格式。所以它**只增字段不删字段**，新增字段一律可选。

## 四、判定规则

| 基线 | 当前 | 判定 | 是否阻断 CI |
| --- | --- | --- | --- |
| pass | fail | `regression` | ✅（配合 `--fail-on-regression`） |
| pass | error | `regression` | ✅ |
| fail / error | pass | `fix` | ❌ |
| pass | pass，相似度 < 阈值 | `drift` | ❌（仅告警） |
| pass | pass，相似度 ≥ 阈值 | `stable_pass` | ❌ |
| fail | fail | `stable_fail` | ❌ |
| 不存在 | 存在 | `new` | ❌ |
| 存在 | 不存在 | `removed` | ❌ |

两个刻意的选择：

1. **`error` 按回归处理**。模型接口挂了和「输出不符合预期」在业务上是同一类事故，都不该被静默放过。
2. **`removed` 不阻断**。删用例通常是主动行为（业务下线），但如果删得太多，得分会因为分母变小而虚高——所以报告里单独列出计数，让人看见。

## 五、错误处理分层

```
ProviderError（网络/HTTP/协议）
    └─ runner 捕获 → 该用例 status=error → 继续下一条
SuiteError（用例集格式）
    └─ cli 捕获 → 退出码 2，不执行任何模型调用
BaselineError（基线文件）
    └─ cli 捕获 → 退出码 2
```

原则：**能在单条用例内消化的错误，不要上升为整轮失败**；**输入性错误必须在调用模型之前暴露**——避免花钱跑完一轮才发现用例集写错了。

## 六、扩展点

想加新能力时，按这个顺序找位置：

| 想加的东西 | 改哪里 | 注意 |
| --- | --- | --- |
| 新断言类型 | `cases.py` 解析 + `metrics.py` 判定 + 测试 + README 字段表 | 四处必须同步 |
| 新模型提供方 | `providers.py` 实现 `complete()` + `get_provider()` 注册 | 只依赖标准库 |
| 新的输出格式（JUnit XML / HTML） | `report.py` 加一个 `render_*` | 不要动 `compare.py` |
| 并发执行 | 已实现（v0.2.0）：`run_suite(concurrency=N)` | 按 futures 提交顺序取回结果，**不能用 `as_completed`**，否则报告行序随网络抖动变化 |
| 基线自动更新 | `cli.py` 加子命令 | 需要二次确认，避免误覆盖 |

## 七、测试策略

| 层次 | 文件 | 覆盖点 |
| --- | --- | --- |
| 纯函数 | `test_metrics.py` | 归一化边界（空串、纯空白、标点）、相似度对称性、空输出必失败 |
| 解析 | `test_cases.py` | 两种格式、重复 id、坏 JSON 行号、未填占位符 |
| 执行 | `test_runner.py` | 确定性、错误隔离、重试恢复、结果结构 |
| 对比 | `test_compare.py` | 七类变化各一例，含「error 也算回归」 |
| 端到端 | `test_cli.py` | 三个子命令 + 三种退出码 + 报告落盘 |

共 64 个测试，全部用标准库 `unittest`，无 mock 框架——`MockProvider` 本身就是可控的假模型，比打桩更接近真实调用链。并发部分用 `_TrackingProvider` 记录同时在飞的调用数，直接证明「并发真的重叠了」，而不是只断言结果正确。
