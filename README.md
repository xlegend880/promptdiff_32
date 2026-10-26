# promptdiff_32

> 把提示词的每一次改动，变成一次可对比、可回滚的回归测试。

[![CI](https://github.com/xlegend880/promptdiff_32/actions/workflows/ci.yml/badge.svg)](https://github.com/xlegend880/promptdiff_32/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](pyproject.toml)

---

## 这个项目解决什么问题

调提示词是一件「改一个字，全盘皆变」的事。现实中它通常长这样：

1. 线上效果不好，有人在 prompt 里加了一句「请用简洁的语言回答」；
2. 感觉变好了，于是上线；
3. 三天后发现另一个场景的承诺口径被顺手改掉了——退款时效从「3-5 个工作日」变成了「尽快」。

问题不在于改错了，而在于**改动的影响面从来没有被度量过**。单元测试管住了代码，但没有东西管住提示词。

`promptdiff_32` 就是把这件事变成可执行的三步：

```
用例集  ──run──▶  结果 JSON  ──diff──▶  回归清单 + Markdown 报告
   ▲                    │
   └────── 基线 ◀────────┘
```

它不训练模型、不做评测榜单、不联网采样。它只做一件很窄的事：**同一批用例，在改动前后各跑一次，告诉你哪一条从通过变成了不通过。**

---

## 核心概念

| 概念 | 含义 |
| --- | --- |
| **用例（Case）** | 一个输入 prompt + 若干条断言 + 可选权重 |
| **断言（Assertion）** | `expect_contains` / `expect_not_contains` / `max_latency_ms`，全部通过才算用例通过 |
| **基线（Baseline）** | 一次「已知良好」的运行结果，存成 JSON |
| **回归（Regression）** | 基线通过、当前不通过 —— 这是唯一会让 CI 失败的类别 |
| **漂移（Drift）** | 断言仍通过，但输出文本相似度低于阈值 —— 只告警，不阻断 |
| **加权得分** | Σ(通过用例权重) / Σ(全部权重) |

把「回归」和「漂移」分开是关键设计：前者是**确定性问题**，必须拦住；后者是**信号**，可能只是模型换了措辞，交给人判断。

---

## 快速开始

零依赖，不需要安装任何第三方包：

```bash
git clone https://github.com/xlegend880/promptdiff_32.git
cd promptdiff_32

# 离线演示：假模型跑两遍，第二遍会检测出 2 条回归
bash scripts/demo.sh
```

想装成命令：

```bash
pip install -e .
promptdiff --version
```

跑自己的用例集：

```bash
# 1. 第一次：生成基线
promptdiff run --suite examples/cases.jsonl --provider mock --out runs/baseline.json

# 2. 改完提示词：对比基线
promptdiff run --suite examples/cases.jsonl --provider mock \
  --baseline runs/baseline.json \
  --out runs/current.json --report runs/current.md \
  --fail-on-regression
```

---

## 输出长什么样

`scripts/demo.sh` 里 v2 变体模拟了一次「把量化承诺模糊化」的提示词改动，对比报告直接点名：

```
- 基线得分 1.0000 → 当前得分 0.7143（Δ -0.2857）
- 回归 2 · 修复 0 · 漂移 3 · 新增 0 · 移除 0

| 用例 | 变化 | 基线 | 当前 | 相似度 | 说明 |
| --- | --- | --- | --- | --- | --- |
| refund-sla | 措辞漂移 | pass | pass | 0.89 | 断言仍通过，但相似度 0.89 低于阈值 0.90 |
| invoice-window | 回归 | pass | fail | 0.91 | 失败断言: contains:24 小时 |
| refund-quantified | 回归 | pass | fail | 0.89 | 失败断言: contains:3-5 个工作日 |
```

注意第一行：`refund-sla` 的断言是「必须出现『原路退回』」，模糊化之后它**仍然通过**，所以纯断言方案会漏掉它；但相似度掉到 0.89，被 drift 抓到。这就是为什么要同时保留两种信号。

完整报告见 [`docs/example-report.md`](docs/example-report.md)。

---

## 用例格式

支持 JSONL（推荐，逐行 diff 友好）和 JSON。一行一个用例：

```json
{"id": "refund-quantified", "prompt": "我要退货，钱什么时候退回来", "expect_contains": ["3-5 个工作日"], "tags": ["售后", "承诺口径"], "weight": 2}
```

| 字段 | 必填 | 类型 | 说明 |
| --- | --- | --- | --- |
| `id` | ✅ | string | 全局唯一，用作基线对比的主键 |
| `prompt` | ✅ | string | 送给模型的输入 |
| `vars` | | object | 填充 prompt 里的 `{{name}}` 占位符 |
| `expect_contains` | | string \| string[] | 输出中必须出现的片段 |
| `expect_not_contains` | | string \| string[] | 输出中禁止出现的片段 |
| `tags` | | string[] | 分类标签，便于人工筛选 |
| `weight` | | number | 默认 1.0，权重越高对得分影响越大 |
| `max_latency_ms` | | number | 延迟上限，超时判失败 |

断言匹配规则（重要）：

- **忽略大小写**，**忽略全部空白**（中文排版产生的换行、缩进不会造成误判）；
- 但**保留标点**——「3-5 个工作日」和「3至5个工作日」视为不同，这是刻意的：承诺口径的差异恰恰体现在这些细节上；
- 输出为空时，`non_empty` 断言恒为失败，避免 `expect_not_contains` 因为「空输出里确实没有违规词」而假通过。

校验用例集（不调用模型）：

```bash
promptdiff validate --suite examples/cases.jsonl
```

按标签只跑一部分（多个标签取并集）：

```bash
promptdiff run --suite examples/cases.jsonl --provider mock --only-tags 售后,财务
```

过滤后若一条用例都不剩，工具会报错退出（码 2）而不是「零用例满分通过」。

---

## 接入真实模型

任何兼容 `/chat/completions` 的服务都能接，通过环境变量传 key：

```bash
export DEEPSEEK_API_KEY=sk-xxxx

promptdiff run --suite examples/cases.jsonl \
  --provider openai \
  --model deepseek-chat \
  --base-url https://api.deepseek.com \
  --out runs/real.json
```

换成 Moonshot、通义、vLLM、Ollama 只需改 `--base-url` 和 `--model`。key 只从环境变量读取，不落盘、不进日志。

---

## 在 CI 里当卡点用

退出码约定：

| 退出码 | 含义 |
| --- | --- |
| `0` | 运行成功，无回归 |
| `1` | 检测到回归（仅当传了 `--fail-on-regression`） |
| `2` | 用例集非法 / 模型接口报错 / 基线文件损坏 |

```yaml
- name: 提示词回归测试
  env:
    DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
  run: |
    pip install -e .
    promptdiff run --suite tests/cases.jsonl \
      --provider openai --model deepseek-chat \
      --baseline .baseline/main.json \
      --report promptdiff-report.md \
      --fail-on-regression
```

基线文件建议跟代码一起提交（`runs/` 已在 `.gitignore` 中排除，用独立目录如 `.baseline/` 存放）。这样每次 PR 都能看到「这次改动影响了几条用例」。

---

## 目录结构

```
promptdiff_32/
├── promptdiff/
│   ├── cases.py       # 用例加载与校验（带行号的错误提示）
│   ├── metrics.py     # 归一化、相似度、断言判定
│   ├── providers.py   # MockProvider / OpenAICompatibleProvider
│   ├── runner.py      # 执行器，单条失败不中断整轮
│   ├── compare.py     # 基线对比，产出 regression/fix/drift
│   ├── report.py      # Markdown 报告渲染
│   └── cli.py         # 命令行入口与退出码
├── examples/          # 可直接跑的示例用例集
├── tests/             # 64 个单元测试，覆盖到 CLI 退出码
├── docs/              # 架构、用法、分支模型、战略分析
└── scripts/demo.sh    # 离线演示
```

---

## 几个刻意的设计取舍

**为什么零第三方依赖？** 回归测试工具最怕「自己的依赖先坏了」。只用标准库意味着它能塞进任何 CI 容器、任何离线环境，也能在三年后还能跑起来。

**为什么用 difflib 而不是向量相似度？** 向量模型会引入一个不确定的、需要下载权重的、可能变版本的依赖，而它给出的分数还无法解释。difflib 的序列匹配虽然粗糙，但同一份输入永远得到同一个分数，且能定位到具体是哪个片段变了。对于「措辞漂移告警」这个用途，确定性比精度更重要。

**为什么单条用例报错不终止整轮？** 一次网络抖动不应该让整份报告变成空白。错误被记为 `error` 状态，仍然计入报告，并且**在对比时按回归处理**——因为「跑不起来」在生产上就是事故。

**为什么把权重做成用例级而不是断言级？** 断言级权重会让「3 条断言过 2 条」这类中间态变得难以解释。用例级权重对应的是「这条用例在业务上有多重要」，这是人真正能判断的东西。

**并发时为什么一定要保序？** 用线程池时最省事的写法是 `as_completed`——谁先跑完谁先出。但报告是按行 diff 的，行序一变，两次运行的对比就全是噪声，连「哪条用例真的变坏了」都看不出来。所以这里坚持按提交顺序取回结果，代价是等待最慢的那一条，收益是报告永远可比。

---

## 路线图

- [x] v0.1.0：用例集、断言、基线对比、Markdown 报告、CI 退出码
- [x] v0.2.0：并发执行（`--concurrency N`），200 条用例从分钟级降到秒级，结果顺序保持不变
- [ ] v0.3.0：多模型 A/B 对比（同一用例集跑两个模型，产出交叉表）
- [ ] v0.4.0：`--update-baseline` 交互式确认，减少手工维护基线
- [ ] 长期：支持 `pytest` 插件形态，让提示词断言和代码断言写在同一个测试文件里

路线图的取舍逻辑见 [`docs/strategy-wu-kan-san-ding.md`](docs/strategy-wu-kan-san-ding.md)。

---

## 项目分析

为什么这个项目长成现在这样、为什么明确拒绝做平台与 SaaS——见 [五看三定战略分析](docs/strategy-wu-kan-san-ding.md)。那份文档里的「不做清单」，就是本项目的边界。

## 参与贡献

欢迎 issue 和 PR，请先读 [CONTRIBUTING.md](CONTRIBUTING.md) 与 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。
分支模型、合并与冲突解决的真实记录在 [`docs/branching.md`](docs/branching.md)。

```bash
python -m unittest discover -s tests -t .   # 全部测试
```

## 许可证

[MIT](LICENSE) © 2026 fzx
