## 这个 PR 做了什么

<!-- 一句话说清改动本身，不要复述 diff -->

## 解决什么问题

<!-- 关联 issue：Closes #12 -->

## 对基线的影响

<!-- 这一栏是必填的：改了 metrics / compare / 断言语义，历史基线会整体漂移 -->

- [ ] 无影响（纯文档 / 纯重构 / 新增可选字段）
- [ ] 有影响，说明：____

## 测试

- [ ] `python -m unittest discover -s tests -t .` 通过
- [ ] `bash scripts/demo.sh` 能跑出预期的 2 条回归
- [ ] 新增/修改的断言类型已同步 README 字段表

## 检查清单

- [ ] 未新增第三方运行时依赖（或已在 issue 中讨论通过）
- [ ] 提交信息符合 Conventional Commits 约定
- [ ] 已从最新 main 切出分支，无多余 merge commit
