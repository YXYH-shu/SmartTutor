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

## 模型配置

- 安全五阶段、备用 `safety_monitor` 与 `emotion_analyzer` 使用 `deepseek-v4-flash-0731`。
- 其余 Agent 和决策节点沿用 `feat/lpp-integration` 的 `glm-5.2`。
- 所有 Agent 使用 DMX OpenAI 兼容地址 `https://www.dmxapi.cn/v1`，API Key 继续从全局环境变量读取。
- 各 Agent 原有温度、token 上限、超时、重试和 thinking 配置保持不变。

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

- `student_id`：优先从用户本轮明确提供的学生编号读取，其次读取 `user_profile.preferences.kt_student_id`，当前集成验证阶段缺失时使用配置默认值 `43`。
- `targets`：可选知识点目标。
- `history_context`：可选补充学习历史。

不使用 SmartTutor 用户 UUID 作为 REKT 学生编号。当前集成验证阶段统一以数据集学生 `43` 作为最终兜底；该值通过配置暴露，后续接入正式身份映射时可以关闭或替换。

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

- 学生编号按“显式输入 → 用户画像映射 → 配置默认值 43”解析；三者均不可用时才返回明确提示和空的兼容结构。
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
- 学生编号解析结果默认可落到 `43`；Runtime 失败时不生成模拟事实。
- 不修改预定义工作流结构。

## Prompt 上下文压缩补充设计

### 目标与边界

KT 与 LPP Runtime 必须先按现有算法完整执行，压缩只发生在 Runtime 返回之后、
调用 LLM 之前。不得修改 REKT 推理、预测目标、学生历史读取、LPP 目标题滑窗、
遗传搜索、候选池、补齐策略或 P1～P5 顺序。

### 认知诊断

完整 KT 结果继续保存在执行上下文中，用于最终字段覆盖、数据库持久化、前端展示和
后续程序逻辑。LLM Prompt 不再重复接收完整 `kt_predictions`、
`kt_mastery_rates` 和 `kt_weak_points`，改为只接收一份 `kt_context`：

- `total_count`、`weak_count`、`developing_count`、`mastered_count`；
- 最弱 10 个知识点；
- 中等掌握 5 个知识点；
- 掌握较好 3 个知识点；
- 每个知识点只保留身份、名称、类型、掌握度、状态和证据字段。

选中知识点按 `skill_id` 去重，总数不超过 18。LLM 只负责主题分析、认知归因、
诊断总结、教学建议和知识关系；Runtime 所有事实字段仍在 `finalize_output()` 中
覆盖 LLM 输出。认知诊断模型的 `max_tokens` 固定为 `32768`。

### 学习路径

`LearningPathAgent` 先用完整诊断结果计算薄弱知识点优先级并运行现有 LPP Runtime。
随后传给 LLM 的 `diagnosis_result` 替换为紧凑摘要，只包含诊断总结、教学建议、
统计值和最多 10 个优先知识点。LPP Runtime 的固定五题仍完整传入 Prompt；最终
P1～P5 事实继续由适配层覆盖，不改变算法输出。

### 验证补充

- 认知诊断 Prompt 中最多出现 18 个 KT 知识点，不包含三份完整重复数据。
- 学习路径 Prompt 中最多出现 10 个诊断知识点。
- 两个 Agent 的最终输出仍保留完整 Runtime 事实。
- 学生 43 的 KT 预测数量和 LPP P1～P5 结果与压缩前一致。

## 输出预算与 LPP Prompt 边界补充设计

### 统一输出预算

`cognitive_diagnosis` 与 `learning_path` 两个功能 Agent 的
`max_tokens` 统一为 `16384`。安全、情感、决策、资源推荐、学伴推荐和最终回复类
Agent 保持原有预算，避免无必要地增加延迟和调用成本。前端概览中的静态配置必须与
后端两个功能 Agent 的真实配置一致。

### LPP Prompt 严格白名单

LPP Runtime 仍使用完整认知诊断计算知识点优先级并完整运行现有算法。算法完成后，
传给解释模型的数据只能包含：

- 最多 10 个最低掌握度知识点及诊断统计、总结和建议；
- 当前水平、年级和学习风格，不包含用户画像中的完整 `weak_points`、
  `knowledge_graph` 或 `preferences`；
- 只保留与 P1～P5 知识点匹配的知识图谱节点和这些节点之间的边；
- LPP 目标题、固定 P1～P5 题目以及每题的教学作用，不包含 Runtime diagnostics、
  related questions 或完整知识序列。

完整诊断与完整 LPP Runtime 继续保存在程序上下文中，分别供算法消费和
`finalize_output()` 覆盖最终事实字段，Prompt 压缩不得改变 P1～P5。

### Thinking 空输出处理

JSON 模式下，如果模型 `content` 为空但存在 `reasoning_content`，不得把自然语言推理
直接交给 JSON 解析器。客户端应显式关闭 Thinking 后重试一次；后续仍无 JSON content
时按模型请求失败处理。非 JSON 模式继续允许使用 reasoning 作为文本结果。

### 验证补充

- 两个功能 Agent 的运行时输出预算均为 16384。
- 渲染后的 LPP Prompt 不包含完整画像、Runtime diagnostics 和 related questions。
- JSON 模式下 reasoning-only 响应会触发关闭 Thinking 的重试，并能消费第二次合法 JSON。
- KT 仍输出 334 个状态，LPP 仍输出顺序固定的 P1～P5。
