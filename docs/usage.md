# 使用手册

## 1. 三种典型用法

### 1.1 本地改提示词时（最常用）

```bash
# 改动前
promptdiff run --suite cases.jsonl --provider openai --model deepseek-chat \
  --out runs/before.json

# 改完 prompt 后
promptdiff run --suite cases.jsonl --provider openai --model deepseek-chat \
  --baseline runs/before.json \
  --out runs/after.json --report runs/after.md
```

看 `runs/after.md` 的「与基线的差异」表格，决定是否继续。

### 1.2 CI 里当门禁

```bash
promptdiff run --suite cases.jsonl \
  --provider openai --model deepseek-chat \
  --baseline .baseline/main.json \
  --report promptdiff-report.md \
  --fail-on-regression --quiet
```

`--quiet` 让 stdout 保持干净（报告已经写进文件），回归信息仍会打到 stderr 和 CI 日志里。

### 1.3 换模型时做对照

```bash
# A 模型
promptdiff run --suite cases.jsonl --provider openai --model deepseek-chat --out runs/a.json
# B 模型
promptdiff run --suite cases.jsonl --provider openai --model qwen-plus --out runs/b.json
# 用 A 作基线比 B
promptdiff compare --baseline runs/a.json --current runs/b.json --report runs/a-vs-b.md
```

---

## 2. 写用例的实操建议

**一条用例只验一个意图。** 「退款要多久 + 发票怎么开 + 能不能转人工」塞进一条用例，失败时你无法判断是哪部分坏了。

**断言写给「必须成立的事实」，不要写给「希望的语气」。**
- ✅ `expect_contains: ["3-5 个工作日"]` —— 这是承诺口径，必须一字不差
- ❌ `expect_contains: ["亲切"]` —— 模型措辞千变万化，这种断言只会带来噪声

**用 `expect_not_contains` 守红线。** 这是性价比最高的断言类型：

```json
{"id": "no-overpromise", "prompt": "你们能保证明天到吗",
 "expect_not_contains": ["保证", "100%", "绝对"]}
```

**权重给业务影响，不给断言数量。** 退款时效写错要赔钱，权重 2~3；措辞偏好类，权重 1 甚至 0.5。

**用 `tags` 做分组。** 报告里目前不按 tag 聚合，但 `tags` 会写进结果 JSON，方便你事后用 `jq` 切：

```bash
jq -r '.cases[] | select(.status!="pass") | "\(.id)\t\(.assertions)"' runs/after.json
jq -r '[.cases[] | select(.tags? // [] | index("售后"))] | length' runs/after.json
```

---

## 3. 基线怎么管

**基线要进版本库，但要和产物分开。** 建议：

```
.baseline/
  main.json          # 跟着 main 分支走的基线
  release-0.1.json   # 发布时的快照
runs/                # 已在 .gitignore 里，本地随便跑
```

**什么时候更新基线：**

- 提示词改动**确认是想要的**，且差异表里没有意外回归 → 用当前结果覆盖基线；
- 换模型 → 单独存一份新基线，不要覆盖旧的，否则跨模型的对比就断了；
- 删用例 → 基线里那条会变成 `removed`，属于预期，直接覆盖即可。

**不要用「删掉失败用例」来让 CI 变绿。** 报告里 `removed` 计数就是为这件事留的证据。

---

## 4. 报告怎么读

一份完整报告包含三块：

1. **结论**：加权得分、通过数、基线对比结论（一句话告诉你能不能合）；
2. **用例明细表**：每条的延迟、断言通过数、输出摘要；
3. **失败详情**：失败断言名 + 输入原文 + 输出原文，直接复制去改提示词。

如果只看一个数字，看 `score` 的 **Δ**，而不是绝对值。绝对值取决于你的用例集难度，Δ 才是这次改动的净影响。

---

## 5. 常见问题

**Q：能测多轮对话吗？**
当前版本不支持。`Case.prompt` 是单条字符串。多轮需要引入消息数组，属于 v0.3 之后的事——先把单轮做扎实。

**Q：为什么延迟数字在 mock 下看起来像真的？**
`MockProvider` 用 prompt 的哈希造了一个 80~240ms 的确定性延迟，目的是让报告结构完整、便于验证延迟断言逻辑，不是真实测量。真实延迟只在 `--provider openai` 下才有意义。

**Q：报告里相似度 0.91 却被判为回归，0.89 反而只是漂移？**
判定的第一依据是**断言**，相似度只在「断言都通过」时才参与判断（用于发现漂移）。断言失败就是回归，跟相似度无关。

**Q：用例集能复用同一份 prompt 配不同断言吗？**
可以，`id` 不同即可。但更推荐把差异放进 `vars`，让用例意图保持单一。

**Q：能只跑某几条用例吗？**
可以，按 `tags` 过滤：`--only-tags 售后,财务`（多个标签取并集）。过滤后一条都不剩会直接报错退出（码 2）——「什么都没跑」在 CI 里会以满分通过，那是最危险的假绿灯。
需要按 id 精确挑选时，仍可以用 `jq` 造一份临时用例集：

```bash
jq -c 'select(.id | startswith("refund"))' cases.jsonl > /tmp/sub.jsonl
```

**Q：中文以外的场景能用吗？**
能。断言匹配只做小写化和去空白，对英文、日文都成立；相似度用字符级序列匹配，对无空格语言（中日）反而比按词切分更稳。

---

## 6. 命令速查

```
promptdiff run      --suite F [--provider mock|openai] [--model M] [--base-url U]
                    [--out F] [--report F] [--baseline F] [--sim-threshold N]
                    [--only-tags T] [--retries N] [--fail-on-regression] [--quiet]
promptdiff compare  --baseline F --current F [--sim-threshold N] [--report F]
promptdiff validate --suite F [--only-tags T]
promptdiff --version
```
