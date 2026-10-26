# 分支管理与冲突解决实录

这份文档记录的是**真实发生过的操作**，不是教科书式的建议。所有哈希都能在 `git log` 里查到，可以逐步复现。

## 一、分支模型

| 分支 | 用途 | 生命周期 |
| --- | --- | --- |
| `main` | 唯一长期分支，始终可发布、CI 始终为绿 | 永久 |
| `feat/<主题>` | 新功能 | 合并后删除 |
| `fix/<主题>` | 缺陷修复 | 合并后删除 |
| `docs/<主题>` | 纯文档 | 合并后删除 |
| `chore/<主题>` | 构建、CI、依赖 | 合并后删除 |

两条硬规则：

1. **不直接推 `main`**。所有改动走分支 + PR，包括改错别字。
2. **合并用 `--no-ff`**。快进合并会把分支拓扑压平，事后无法回答「这批改动是一个整体吗」。多一个 merge commit 换来的是可追溯性，很划算。

## 二、一次完整的功能分支流程

以 `feat/tag-filter`（新增 `--only-tags` 按标签筛选用例）为例：

```bash
# 1. 从最新 main 切出
git checkout main && git pull
git checkout -b feat/tag-filter

# 2. 开发：改代码 + 补测试 + 同步文档（三件事必须一起做）
#    promptdiff/cases.py      新增 filter_by_tags()
#    promptdiff/cli.py        新增 --only-tags 参数
#    tests/test_cases.py      +4 个测试
#    tests/test_cli.py        +3 个测试
#    README.md / docs/usage.md / CHANGELOG.md  同步

# 3. 自测
python -m unittest discover -s tests -t .
# Ran 57 tests ... OK

# 4. 提交
git add -A
git commit -m "feat(cli): 支持 --only-tags 按标签筛选用例"

# 5. 合并回 main（保留拓扑）
git checkout main
git merge --no-ff feat/tag-filter -m "merge: 合并 feat/tag-filter 到 main"

# 6. 删除已合并分支
git branch -d feat/tag-filter
```

实际产生的提交：

```
*   57e24f3 merge: 合并 feat/tag-filter 到 main
|\
| * 152a208 feat(cli): 支持 --only-tags 按标签筛选用例
|/
* e2d5460 ci: GitHub Actions 测试矩阵与离线演示任务
```

这个功能里有一个值得说明的设计决定：**过滤后为空时抛错而不是返回空列表**。因为空用例集会让 CI 以「100% 通过」结束——比失败更危险，它是一条假绿灯。分支评审时这条被单独讨论过，最后写进了 CHANGELOG。

## 三、一次真实的合并冲突

### 3.1 冲突是怎么产生的

两个人（这里是同一人的两个并行任务）从同一个 `main` 切出，都去改差异报告的表格：

- `feat/report-similarity-3f`：把相似度列从两位小数改成三位小数（`{sim:.2f}` → `{sim:.3f}`），表头加单位 `相似度(0~1)`；
- `feat/report-detail-width`：把「说明」列截断宽度从 80 字放宽到 120 字，表头标注 `说明（截断 120 字）`。

两条改动**语义上完全正交**，但都落在 `promptdiff/report.py` 的同一行表头上，也都在 `CHANGELOG.md` 的 `### 新增` 下插入了新条目。于是：

```
$ git checkout feat/report-similarity-3f
$ git merge feat/report-detail-width

Auto-merging CHANGELOG.md
CONFLICT (content): Merge conflict in CHANGELOG.md
Auto-merging promptdiff/report.py
CONFLICT (content): Merge conflict in promptdiff/report.py
Automatic merge failed; fix conflicts and then commit the result.
```

### 3.2 冲突现场

`promptdiff/report.py`：

```
<<<<<<< HEAD
        "| 用例 | 变化 | 基线 | 当前 | 相似度(0~1) | 说明 |",
=======
        "| 用例 | 变化 | 基线 | 当前 | 相似度 | 说明（截断 120 字） |",
>>>>>>> feat/report-detail-width
```

`CHANGELOG.md`：

```
<<<<<<< HEAD
- 差异报告的相似度列改为三位小数：阈值附近 0.89 与 0.90 在两位小数下看不出差别，无法判断是否越界。
=======
- 差异报告的「说明」列截断宽度由 80 字放宽到 120 字：断言失败原因经常在 80 字之后才说到点上。
>>>>>>> feat/report-detail-width
```

注意 `git status` 里这两个文件是 `UU`（both modified）——两侧都改过，Git 没有自动裁决的依据。

### 3.3 怎么解

**关键判断：这不是「二选一」，而是「两个都要」。** 冲突的本质是两处改动恰好共享一行文本，不是两个需求互斥。

所以解法是**合并语义**，而不是挑一侧：

```python
# 解决后
"| 用例 | 变化 | 基线 | 当前 | 相似度(0~1) | 说明（截断 120 字） |",
```

CHANGELOG 则是两条都留、按逻辑顺序排列。

有个细节值得说：`{sim:.3f}` 和 `detail=_cell(..., 120)` 这两行**没有冲突**——它们在文件里相隔较远，Git 自动合并了。只有表头这一行真的撞了。**冲突范围通常远小于「两个分支都改了这个文件」给人的心理预期**，所以第一件事永远是看 `git status`，而不是放弃重来。

### 3.4 解完必须做的事

```bash
# 1. 搜一遍有没有漏掉的冲突标记
grep -rn '<<<<<<<\|>>>>>>>' promptdiff/ CHANGELOG.md
# （无输出才算干净）

# 2. 跑测试 —— 冲突解决最容易引入的是语法错误和逻辑半残
python -m unittest discover -s tests -t .
# Ran 57 tests ... OK

# 3. 提交，并在提交信息里写清「怎么解的、为什么」
git add -A
git commit -m "merge: 合并 feat/report-detail-width，解决报告列冲突"
```

合并提交的完整信息里写明了解决依据：

> 两条改动正交：一条把相似度精度提到三位小数，一条把说明列宽度放到 120 字。冲突在表头行与 CHANGELOG 同一插入点，解决方式是同时保留两侧语义，表头合并为「相似度(0~1) | 说明（截断 120 字）」，格式串取 `{sim:.3f}` 与 120 字截断。

### 3.5 最终拓扑

```
*   ee83d83 merge: 合并报告可读性改进（含冲突解决）到 main
|\
| *   1b43599 merge: 合并 feat/report-detail-width，解决报告列冲突
| |\
| | * 4f0742d feat(report): 说明列截断宽度放宽到 120 字
| * | 4314ba6 feat(report): 相似度列改为三位小数
| |/
*   57e24f3 merge: 合并 feat/tag-filter 到 main
```

## 四、解决冲突的三条原则

**1. 先读，再改。** 直接删掉 `<<<<<<<` 留下的那一侧，等于随机丢弃一个人的工作。先把两侧的提交信息读一遍，搞清各自想解决什么问题。

**2. 优先合并语义，其次才取舍。** 绝大多数冲突是「同一行被两个人改了」，而不是「两个需求互斥」。真正互斥时，才需要判断哪一侧优先，并且必须在提交信息里写清理由——三个月后回来看的人只有这条线索。

**3. 解决完必须跑测试。** 冲突解决是唯一一种「Git 认为成功了但代码可能已经坏了」的合并方式。文本层面的标记清干净了，逻辑层面可能还是断的。

## 五、几个实用命令

```bash
# 看当前冲突了哪些文件
git status --short          # UU 表示 both modified

# 看某个文件两侧分别改了什么
git diff --diff-filter=U

# 明确放弃这次合并，回到合并前
git merge --abort

# 只想看对方分支在这个文件里改了什么
git log --oneline HEAD..feat/xxx -- promptdiff/report.py

# 找是谁改了某一行（定位冲突责任人时用）
git log -L 50,52:promptdiff/report.py

# 合并后确认分支真的合并进去了
git branch --merged main
```

## 六、复现本文档中的历史

```bash
git clone https://github.com/xlegend880/promptdiff_32.git
cd promptdiff_32

git log --oneline --graph --all          # 看完整拓扑
git show 1b43599                         # 看冲突解决的合并提交
git show 152a208 --stat                  # 看功能分支改了哪些文件
git log -L 50,52:promptdiff/report.py    # 看表头那一行的演变
```

分支已被删除（`git branch -d` 只删引用，提交对象仍在），所以复现时用哈希而不是分支名。
