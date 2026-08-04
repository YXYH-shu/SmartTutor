# KT 与 LPP 原生字段适配设计

## 目标

在不修改 SmartTutor 预定义工作流结构的前提下，将真实 KT 认知诊断和 LPP 路径规划能力接入现有 `cognitive_diagnosis` 与 `learning_path` Agent。两个 Agent 输出符合 `main` 已有字段契约，供现有上下文传递、用户画像、SSE 和前端面板直接消费。

## 范围

本次实现只负责：

- `cognitive_diagnosis` 调用 KT Runtime，并把真实结果映射到原诊断字段。
- `learning_path` 调用 LPP Runtime，并把固定 P1～P5 推荐映射到原路径字段。
- 修正 KT/LPP 使用的学生编号解析，不把 SmartTutor 用户 UUID 当作 REKT 学生编号。
- 为后端与前端已有字段名差异提供兼容别名。
- 增加配置、测试和必要的运行说明。

本次不负责：

- 修改 `backend/config/workflows.yaml` 中的预定义工作流。
- 重写安全策略、情感分析、知识回复、内容润色或共情 Agent。
- 新增独立 iframe 页面或旁路 ChatAgent 服务。
- 让 LLM 生成或改写 KT 掌握度、LPP 推荐题及其顺序。

## 固定图节点

保留现有图结构：

```text
每轮消息
  -> safety_check
     -> SAFE / TRANSFORM: emotion_preprocess -> decide -> 原工作流
     -> SOFT_BLOCK / HARD_BLOCK / REFERRAL: assemble_response -> 结束
```

安全检查每轮执行。情感分析在所有未被安全策略直接拦截的轮次执行；`TRANSFORM` 后对安全改写后的消息继续进行情感分析。该行为已经由现有 LangGraph 图保证，不做修改。

## 认知诊断契约

### 输入

SmartTutor 已有输入继续保留：

- `recent_messages`
- `current_message`
- `student_grade`
- `learning_traces`
- `knowledge_graph`
- `existing_mastery`
- `existing_knowledge_points`
- `user_profile`

适配层额外解析 KT Runtime 所需信息：

- `student_id`：优先从用户本轮明确提供的学生编号读取，其次读取 `user_profile.preferences.kt_student_id`。
- `targets`：可选知识点目标。
- `history_context`：可选补充学习历史。

找不到合法 REKT 学生编号时返回明确的不可用结果，不使用 SmartTutor 用户 UUID 兜底。

### 输出

保持后端 YAML 必填字段：

- `topic_analysis`
- `knowledge_states`
- `cognitive_attribution`
- `weak_points`
- `diagnosis_summary`
- `recommended_actions`
- `knowledge_graph`

同时保留代码和前端实际消费的集成字段：

- `mastery_rates`
- `diagnosis_source`
- `kt_metrics`
- `kt_model_info`

`knowledge_states` 每项至少包含：

- `skill_id`
- `skill_name`
- `type`
- `mastery_percent`
- `mastery_label`

可附带 `mastery_rate`、`status`、`source_basis`、`relation_to_query`、`evidence`、`priority` 和 `safety_ethic_assessment`。

### 数据所有权

KT Runtime 是以下字段的唯一事实来源：

- `knowledge_states` 中的知识点身份和掌握度
- `mastery_rates`
- `weak_points`
- `diagnosis_source`
- `kt_metrics`
- `kt_model_info`

LLM 只补充：

- `topic_analysis`
- `cognitive_attribution`
- `diagnosis_summary`
- `recommended_actions`
- `knowledge_graph`

合并时以 KT 字段覆盖 LLM 同名字段。

## 路径规划契约

### 输入

SmartTutor 已有输入继续保留：

- `current_message`
- `recent_messages`
- `diagnosis_result`
- `knowledge_graph`
- `goal`
- `time_available`
- `current_level`
- `user_profile`

当 `goal` 缺失时，以 `current_message` 作为学习目标。适配层从 `diagnosis_result.mastery_rates`、`diagnosis_result.weak_points` 或用户画像中的最近 KT 数据提取薄弱知识点优先级，并解析可选 `target_question_id`。

### 输出

保持后端 YAML 必填字段：

- `planning_rationale`
- `learning_path`
- `total_estimated_time`
- `adaptive_rules`

保持原 schema 的可选字段：

- `main_path_sequence`
- `optional_branch`
- `risk_correction`
- `milestones`
- `path_adjustment_triggers`

每个 `learning_path` 阶段至少包含：

- `stage_id`
- `name`
- `objective`
- `skills`
- `duration_min`
- `checkpoints`

每个 `skills` 项至少包含：

- `skill_id`
- `skill_name`
- `priority`
- `reason`

为兼容前端现有配置，同时返回：

- `stages`：与 `learning_path` 引用同一阶段数据。
- `estimated_completion`：与 `total_estimated_time` 表达同一完成时间。

为保留 LPP 固定五题的完整机器可读事实，增加可选扩展字段：

- `recommended_questions`：顺序固定为 P1～P5，包含题号、题干、题型、选项和知识点等 Runtime 已提供数据。
- `lpp_source`：标记结果来自真实 LPP Runtime 或不可用状态。

### 数据所有权

LPP Runtime 是以下内容的唯一事实来源：

- P1～P5 题目集合
- P1～P5 顺序
- 题干、题型、选项和关联知识点
- Runtime 提供的预测概率或评分

LLM 可以生成路径解释和教学建议，但不能新增、删除、替换、重排或改写推荐题。适配层在最终合并时重新覆盖 `recommended_questions`，保证事实不受 LLM 输出影响。

## 上下文传递

保持现有 `stage_executor` 行为：

```text
cognitive_diagnosis output
  -> context["cognitive_diagnosis"]
  -> diagnosis_result
  -> mastery_rates
  -> knowledge_graph
  -> learning_path input

learning_path output
  -> context["learning_path"]
  -> learning_plan
  -> 现有后续 Agent（若工作流包含）
```

不引入新的工作流节点或旁路响应流程。

## 错误处理

- 学生编号缺失：返回明确提示和空的兼容结构，不生成模拟掌握度或模拟推荐题。
- KT Runtime 失败：返回不可用状态；LLM 可以解释失败原因，但不得生成模拟掌握度。
- LPP Runtime 失败：返回 `lpp_source = "lpp_unavailable"` 和空路径/空推荐题，不让 LLM伪造五题。
- Runtime 返回非五题、顺序非 P1～P5 或缺少题干时，视为无效结果。
- 可选扩展字段不得改变原 YAML 必填字段的类型。

## 实现边界

优先复用 `feat/lpp-integration` 中已验证的 Runtime、数据读取和算法代码，但不直接搬迁该分支对工作流、SSE、前端页面、Prompt 总体结构和报告渲染的改造。迁移内容以本设计定义的字段适配边界为准。

## 验证标准

- 原有安全与情感固定节点测试继续通过。
- KT 输出能通过认知诊断 schema，并且真实数值覆盖 LLM 同名字段。
- 认知诊断结果能自动成为 LPP 的 `diagnosis_result`。
- LPP 输出同时包含 `learning_path` 和 `stages`，内容一致。
- `recommended_questions` 恰好五项且顺序为 P1～P5。
- LLM 返回篡改题目时，最终结果仍保持 Runtime 原题和顺序。
- 学生编号缺失或 Runtime 失败时不生成模拟事实。
- 不修改预定义工作流结构。
