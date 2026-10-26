# 贡献指南

感谢你愿意花时间改进 promptdiff_32。这个项目刻意保持小，所以贡献流程也尽量短。

## 环境准备

```bash
git clone https://github.com/xlegend880/promptdiff_32.git
cd promptdiff_32
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

项目**不引入任何运行时第三方依赖**，只用标准库。提 PR 时请不要新增 `dependencies`——如果确实需要，先在 issue 里讨论清楚理由。

## 分支模型

| 分支 | 用途 | 生命周期 |
| --- | --- | --- |
| `main` | 唯一长期分支，始终可发布 | 永久 |
| `feat/<主题>` | 新功能 | 合并后删除 |
| `fix/<主题>` | 缺陷修复 | 合并后删除 |
| `docs/<主题>` | 纯文档改动 | 合并后删除 |
| `chore/<主题>` | 构建、CI、依赖等 | 合并后删除 |

约定：

1. **不直接推 main**。所有改动走分支 + PR，包括文档。
2. 分支从最新的 `main` 切出，命名用短横线小写英文，如 `feat/concurrency`。
3. 合并统一用 `--no-ff`（保留分支拓扑），见 [`docs/branching.md`](docs/branching.md)。
4. 合并前先 `git rebase main` 或 `git merge main` 解决落后，不要在 PR 里留下无意义的 merge commit。

## 提交信息

采用 Conventional Commits 的简化版，中文正文：

```
feat(cli): 支持 --concurrency 并发执行用例

- 用 ThreadPoolExecutor 控制并发度，默认 1 保持向后兼容
- 结果顺序仍按用例集原始顺序输出，避免报告 diff 噪声

Closes #12
```

类型：`feat` / `fix` / `docs` / `test` / `refactor` / `chore` / `perf`。

## 提 PR 之前

```bash
# 1. 全部测试必须通过
python -m unittest discover -s tests -t .

# 2. 演示脚本必须能跑通（它会验证「回归能被检出」这条主链路）
bash scripts/demo.sh

# 3. 改了 CLI 行为，记得同步 README 的退出码表
```

PR 描述请回答三个问题：

- 这个改动解决了什么问题？
- 有没有可能破坏已有的基线对比结果？（比如改了 `similarity` 算法，历史基线会全部漂移）
- 测试覆盖了哪些边界？

## 代码风格

- PEP 8，行宽 120；
- 类型标注尽量加，文件顶部统一 `from __future__ import annotations`（保持 3.9 兼容）；
- 注释写「为什么」，不写「做了什么」——代码本身已经说明做了什么；
- 中文注释与中文文档是本项目的一等公民，不必翻译成英文。

## 新增断言类型

如果你要加新的断言，请同时改这四处，否则会留下不一致：

1. `promptdiff/cases.py` —— 字段解析与校验；
2. `promptdiff/metrics.py` —— 判定逻辑；
3. `tests/test_metrics.py` —— 至少一个正例、一个反例；
4. `README.md` —— 字段表。

## 报告安全问题

请勿用公开 issue 报告安全漏洞，流程见 [SECURITY.md](SECURITY.md)。
