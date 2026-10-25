---
name: lpp-skill
description: 为教师生成学习路径规划和固定 5 题推荐序列。用于用户要求按学生与目标题规划练习、解释 P1-P5 的教学作用与知识点递进、或把 LPP 运行时 JSON 转换为“教师端说明＋推荐题表格＋原始 JSON”时；纯学情诊断且不需要推荐题序列时不要使用。
---

# LPP Skill

## 目标

读取 LPP 运行时结果，为教师生成可信、可执行、可追溯的学习路径说明。严格区分：

- 运行时负责确定目标题、5 道主推荐题、知识点前后序和关联题；
- Agent 负责解释路径、生成固定表格，并原样透传运行时 JSON；
- 不让 Agent 改写推荐集合、补造数据或解释内部算法过程。

## 工作流

1. 获取运行时 JSON。
   - 用户已提供 JSON 时，直接使用该对象，不重复运行。
   - 用户要求为学生实际生成路径但未提供 JSON 时，先阅读
     [references/runtime-guide.md](references/runtime-guide.md)，再按其中的默认 CPU 方式运行。
2. 检查 `status` 与 `message`。
   - 仅当 `status` 为 `ok` 且 `message` 为 `recommendations_ready` 时生成完整规划。
   - 其他状态只说明运行时结果，不强行生成 5 题路径。
3. 校验主推荐题。
   - `recommendation.questions` 必须恰有 5 项。
   - `order` 必须连续为 1～5。
   - 每题必须有题干、题型和至少一个知识点。
   - 校验失败时报告数据契约错误，不补题、不换题。
4. 生成教师端输出前，完整阅读：
   - [references/output-contract.md](references/output-contract.md)：硬性格式和推理边界；
   - [references/teacher-output-example.md](references/teacher-output-example.md)：语气、长度和详略标准。
5. 按输出契约生成三部分：
   - 教师端自然语言说明；
   - 按 `order` 排列的 5 行推荐题表格；
   - 运行时 stdout 中的原始 JSON 对象。

## Runtime Command

Work from the skill directory:

```bash
cd services/lpp-skill
```

Default student-ID mode requires:

- `student_id`: 学生标识；SmartTutor 当前集成验证默认使用 `43`

Optional context:

- `target_question_id`: 起始题目 ID；不传时从学生序列默认位置开始规划

默认用 `KT_DEVICE=cpu KT_ALLOW_CPU_FALLBACK=1 conda run -n kt python scripts/run_lpp.py` 执行学习路径规划运行时。

Default student-ID planning:

```bash
KT_DEVICE=cpu KT_ALLOW_CPU_FALLBACK=1 conda run -n kt python scripts/run_lpp.py --student-id 43
```

Include `--target-question-id` only when the user has already provided a concrete target question:

```bash
KT_DEVICE=cpu KT_ALLOW_CPU_FALLBACK=1 conda run -n kt python scripts/run_lpp.py \
  --student-id 43 \
  --target-question-id 774
```

## 核心约束

- 只把 `recommendation.questions` 中的 5 道题作为主推荐题，并严格按 P1～P5 排序。
- 题号只能作为辅助标识；始终展示完整题干、题型和知识点。
- `options` 为空时明确写“题库暂未提供选项”；不编造选项、答案或解析。
- 只依据 `target`、推荐题、`plan_items`、知识点目录顺序和关联题解释路径。
- 不推断学生未提供的错误原因、学习行为、能力缺陷或知识掌握结论。
- 只有数据支持时才描述知识递进；知识点切换或不存在可靠关系时，如实说明主题切换，
  不强行构造递进。
- 自然语言和表格不得暴露遗传算法、候选池、ACE 排名或其他内部诊断过程。
- 第三部分 JSON 不重组、不摘要、不新增字段，也不把 Agent 生成的自然语言写回 JSON。
- 在沙盒中调用运行时时，必须使用 `KT_DEVICE=cpu KT_ALLOW_CPU_FALLBACK=1`
  和 conda 环境 `kt`；不要默认请求 GPU。

## 开发与维护路由

- 执行运行时、调整命令参数或排查运行状态：阅读
  [references/runtime-guide.md](references/runtime-guide.md)。
- 修改教师端输出规则或示例：只改 `references/output-contract.md` 与
  `references/teacher-output-example.md`，同时检查本文件中的核心约束是否仍一致。
- 修改架构、模型适配器或搜索实现前：阅读 SmartTutor 仓库根目录的
  `AGENTS.md`；不要为输出格式需求修改算法。
- 保持 `scripts/run_lpp.py` 的 stdout 为单个 JSON 对象，不混入教师端文字或日志。
