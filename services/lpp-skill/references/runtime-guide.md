# LPP 运行与开发参考

## 运行环境

使用 conda 环境 `kt`。不要用 `base` 环境或系统 `python3` 直接运行。

默认使用 KT 后端和 CPU。沙盒没有可用 GPU，因此每次运行都必须设置
`KT_DEVICE=cpu KT_ALLOW_CPU_FALLBACK=1`：

```bash
cd services/lpp-skill
KT_DEVICE=cpu KT_ALLOW_CPU_FALLBACK=1 \
  conda run -n kt python scripts/run_lpp.py \
  --student-id 43 \
  --target-question-id 774
```

不传可选的题目 ID 时，默认从该学生第 11 道题开始滑窗：

```bash
KT_DEVICE=cpu KT_ALLOW_CPU_FALLBACK=1 \
conda run -n kt python scripts/run_lpp.py \
  --student-id 43
```

固定随机种子并调整搜索参数：

```bash
KT_DEVICE=cpu KT_ALLOW_CPU_FALLBACK=1 \
conda run -n kt python scripts/run_lpp.py \
  --student-id 43 \
  --target-question-id 774 \
  --length 10 \
  --pop-size 50 \
  --max-gen 100 \
  --weights 0.9,0.1 \
  --top-k-knowledge 5 \
  --min-sample 5 \
  --seed 42
```

## 参数口径

SmartTutor 对话内规划会启用主题约束模式：`--topic-skill-ids` 接收本轮语义检索确认的
有序知识点 ID，所有目标题、候选练习、邻接知识和五阶段结果都限定在该集合内。
此模式下 `--preferred-skill-ids` 由本轮核心知识点组成，核心内按真实学情排序；
无对应历史题时选用真实题库目标，不补造学生作答。明确目标或核心目标不会因预测
掌握度较高而漂移到其他主题点。相关知识点或题目不足时明确失败，不跨主题补齐。
不传 `--topic-skill-ids` 时保留下面的历史滑窗行为。

- `--student-id`：学生标识。
- `--target-question-id`：从学生做题序列末尾向前定位该题最后一次出现的位置，并以此
  作为滑窗起点。不传时从第 `length+1` 道题开始。
- `--length`：每次预测使用目标题之前最多多少条历史交互，默认 10。
- `--top-k-knowledge`：内部选择练习时参考的知识点数量，不对教师展示。
- `--min-sample`：内部统计的最小采样次数，不对教师展示。
- `--seed`：固定随机种子，使结果可复现。

若当前题预测正确率不低于 0.5，运行时会继续检查下一题；到达序列最后一道题时仍会
执行规划。不要在教师端解释这一内部滑窗过程。

## 运行时输出

stdout 必须是单个 JSON 对象：

- `status`：`ok` 或 `error`；
- `message`：`recommendations_ready` 时可生成完整教师端规划；
- `target`：最终目标题及预测概率；
- `recommendation.questions`：固定 5 道主推荐题；
- `plan_items`：每题的目的、知识点前后序和关联题；
- `diagnostics`：仅用于运行排查，不写入教师端自然语言或表格。

## 开发边界

- 生产后端仅使用仓库内 `kt-runtime-skill` 提供的 KT 模型与数据。
- 新增知识追踪后端时实现 `KTScorer`，不要复制或改写搜索算法。
- 不要为教师端格式需求修改 `scripts/run_lpp.py`、模型适配器或搜索实现。
- 不要修改 `kt-runtime-skill` 或 `LPP/DSMOEA` 来临时兼容本 Skill。
- 候选题不足时允许搜索层有放回采样；展示层只使用运行时给出的 5 道主推荐题。

## 验证

修改算法或模型适配器后运行：

```bash
conda run -n kt pytest tests/test_target_selection.py -q
KT_DEVICE=cpu KT_ALLOW_CPU_FALLBACK=1 \
conda run -n kt python scripts/run_lpp.py --student-id 43 --seed 42
```

仅修改 Skill 提示词、输出契约或示例时，不需要运行模型回归测试，但必须验证 Skill
结构，并确认 `scripts/` 与 `tests/` 没有被修改。
