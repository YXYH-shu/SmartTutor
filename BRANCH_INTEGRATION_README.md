# 安全监测与内容矫正智能体更新

本分支增加安全监测智能体和内容矫正智能体，以及两者接入 LangGraph 所需的状态、节点、事件和前端交互。其他教育智能体的实现与提示词保持不变。

## 1. 安全监测智能体

### 功能与工作原理

安全监测智能体位于每轮对话入口，输出三种处理结果：

| `branch` | 处理方式 |
|---|---|
| `PASS` | 原问题不改写，进入原教育智能体链路 |
| `GUIDE` | 调用教育转化 Skill，将风险问题转成安全、适龄的两阶段学习任务 |
| `REJECT` | 返回安全拒绝或危机关怀，不进入教学链路 |

处理过程：

1. 主分类模型同时识别风险类别、请求类型、操作性、危机信号和重复绕过行为。
2. 本地确定性规则处理明确高风险、危机、底线违规和无害制作等高置信场景。
3. 主分类不确定、结果冲突或疑似漏放时，调用独立裁决模型复核。
4. `PASS` 直接放行；`REJECT` 直接生成教师口吻的安全回复。
5. `GUIDE` 调用 `safety-education-guidance` Skill，一次生成 2～3 个学科方向，以及每个学科下的 2～3 个知识点。
6. 学生先选择学科，再选择知识点；完成后只把 `safe_query` 交给教学链路。
7. 分类、裁决、Skill 或结构化解析失败时，使用本地安全兜底，不返回空结果。

### 输入字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `raw_text` | `string` | 原始学生输入，最高优先级 |
| `current_message` | `string` | 当前消息，`raw_text` 缺失时使用 |
| `message` | `string` | 兼容输入字段 |
| `student_grade` | `string` | 学段或年级 |
| `grade_level` | `string` | 兼容学段字段 |
| `user_age` | `string/number` | 学段字段均缺失时的兼容信息 |
| `recent_messages` | `array` | 最近对话；最多取最后 6 条组成分类上下文 |

### 输出字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `branch` | `PASS/REJECT/GUIDE` | 最终安全分支 |
| `reject_type` | `string/null` | 拒绝类型，如 `CRISIS`、`MORAL_BOTTOM_LINE` |
| `safe_query` | `string/null` | GUIDE 转化后的安全学习问题 |
| `learning_options` | `string[]` | 当前阶段向学生展示的 2～3 个选项 |
| `recommended_option` | `string/null` | 推荐选项，必须属于 `learning_options` |
| `direct_response` | `string/null` | REJECT 或 GUIDE 直接展示的教师式回复 |
| `safety_context` | `object` | 分类结果、转化结果和后续路由上下文 |

### `safety_context` 主要字段

| 字段 | 说明 |
|---|---|
| `risk_category` | `N/A/B/C/D1/D2/D3` 风险类别 |
| `intent` | 学习、试探、恶意、情绪等意图 |
| `core_topic` | 从原问题中提取的核心主题 |
| `safe_learning_goal` | 保留的安全学习目标 |
| `operational_request` | 是否索取可执行方法、参数或步骤 |
| `original_query` | 原始问题，仅保留在安全上下文中 |
| `forbidden_content` | 后续不得恢复的危险能力信息 |
| `allowed_content` | 安全学习任务中可以保留的普通细节 |
| `classifier` | 主分类或裁决后的完整结构化结果 |
| `guidance_skill` | GUIDE 分支的教育转化 Skill 输出 |
| `resolved_from_guide` | 是否已经完成两阶段选择 |
| `selected_subject_label` | 学生选择的学科方向 |
| `selected_option` | 学生最终选择的知识点 |

### 教育转化 Skill 字段

Skill 输入：

| 字段 | 说明 |
|---|---|
| `original_query` | 原始问题 |
| `core_topic` | 必须保留的具体主题 |
| `safe_learning_goal` | 合法学习目标 |
| `student_grade` | 学段信息 |
| `risk_category` | `A/B/D1/D2/D3` 中可教育转化的类别 |
| `intent`、`risk_reason` | 分类意图和风险原因 |
| `operational_request` | 是否包含可执行危险能力 |
| `conversation_context` | 最近对话上下文 |
| `forbidden_content`、`allowed_content` | 最小删除和安全保留边界 |

Skill 输出：

| 字段 | 说明 |
|---|---|
| `status` | `ok` 或本地兜底使用的 `fallback` |
| `selection_mode` | 固定为 `two_stage` |
| `education_domain` | 科学安全、历史公民、法律伦理、数字素养等教育领域 |
| `safe_query` | 顶层安全学习问题 |
| `learning_options` | 第一阶段学科标签列表 |
| `recommended_option` | 推荐学科标签 |
| `subject_options` | 2～3 个完整学科分支 |
| `preserved_elements` | 从原问题原样保留的主题元素 |
| `transformation_summary` | 最小语义修复说明 |
| `constraints_applied` | 本次实际应用的安全约束 |

每个 `subject_options` 分支包含：

| 字段 | 说明 |
|---|---|
| `school_subject` | 物理、生物、历史、信息技术等标准学科标识 |
| `label` | 第一阶段显示的学科名称 |
| `subject_focus` | 该学科对应的具体研究方向 |
| `safe_query` | 选中该学科后交给后续流程的安全问题 |
| `learning_options` | 第二阶段的 2～3 个知识点 |
| `recommended_option` | 推荐知识点 |

### 附属文件及具体作用

| 文件 | 具体内容 |
|---|---|
| `backend/app/services/agents/safety_monitor.py` | 安全智能体入口；适配输入别名，调用 `SafetyPipeline`，统一返回智能体输出结构 |
| `backend/app/services/safety_pipeline.py` | 主分类、裁决、本地规则、三分支决策、GUIDE 调用和异常兜底的核心实现 |
| `backend/app/services/safety_guidance_skill.py` | 加载教育转化 Skill，校验 JSON，规范学科树，修复危险 `safe_query` 和无效选项 |
| `backend/config/prompts/safety_monitor.yaml` | 智能体注册信息、模型配置和公开输入输出 Schema |
| `backend/config/prompts/safety_classifier.yaml` | 主分类提示词；定义风险类别、请求类型和结构化分类字段 |
| `backend/config/prompts/safety_adjudicator.yaml` | 独立复核提示词；只在主分类低置信、冲突或失败时运行 |
| `services/safety-education-guidance/SKILL.md` | 教育转化原则：保留安全意图，只移除最小危险能力 |
| `services/safety-education-guidance/agents/openai.yaml` | Skill 的模型调用元数据与执行配置 |
| `services/safety-education-guidance/references/contract.md` | 两阶段输出契约、字段约束和合法枚举 |
| `services/safety-education-guidance/references/runtime-prompt.md` | 后端实际加载的转化运行提示词 |
| `services/safety-education-guidance/references/school-subjects.md` | 标准学科标识、显示名称和学科映射规则 |
| `backend/tests/safety_evaluation_dataset.md` | 420 条 PASS、GUIDE、REJECT 安全评测样本 |
| `backend/tests/test_safety_pipeline.py` | 三分支、规则兜底、两阶段转化和异常路径单元测试 |
| `backend/tests/run_safety_evaluation.py` | 安全分支准确率和延迟评测脚本 |
| `backend/tests/run_safety_guidance_evaluation.py` | GUIDE 转化有效率、内容安全和延迟评测脚本 |

## 2. 内容矫正智能体

### 功能与工作原理

内容矫正智能体位于教学回答生成完成之后、最终回复组装之前，执行四项验收：

| 检查字段 | 检查内容 |
|---|---|
| `scientific_reliability` | 事实、概念、术语和因果关系是否可靠 |
| `educational_completeness` | 是否直接回答问题并包含必要解释、依据和边界 |
| `structural_clarity` | 标题、编号、列表和内容层级是否清晰 |
| `content_safety` | 是否遵守上游安全约束且未恢复危险细节 |

验收结果：

| `action` | 处理方式 |
|---|---|
| `PASS` | 忽略模型提供的替代文本，逐字保留原回答 |
| `PATCH` | 仅允许局部修复；修改后长度必须为原文的 75%～135%，且不能减少原有列表结构 |
| `REGENERATE` | 退回 `knowledge_responder` 重写；最多执行一次 |

PATCH 未通过四项检查、修改范围过大或破坏结构时，自动升级为 `REGENERATE`。重写失败时保留最近一次回答；达到一次重写上限后改为 `PASS`，防止 LangGraph 无限回环。

### 输入字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `original_response` | `string` | 必填，待验收的完整教学回答 |
| `student_question` | `string` | 当前学生问题 |
| `subject` | `string` | 当前学科 |
| `grade_level` | `string` | 当前学段 |
| `conversation_stage` | `string` | 当前教学阶段 |
| `safety_constraints` | `object` | 安全监测产生的约束和安全上下文 |

### 模型输出字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `action` | `PASS/PATCH/REGENERATE` | 模型请求的处理动作 |
| `issues` | `string[]` | 发现的问题和重写要求 |
| `patched_response` | `string` | PATCH 后的完整回答；PASS/REGENERATE 时必须为空 |
| `checks` | `object` | 四项验收布尔结果 |

### LangGraph 过程字段

内容矫正节点将以下数据写入 `context.content_corrector`：

| 字段 | 说明 |
|---|---|
| `action` | 经过本地规则校验后的最终动作 |
| `requested_action` | 模型最初请求的动作 |
| `issues` | 问题列表及本地追加原因 |
| `patched_response` | 实际采用的局部修正文本 |
| `checks` | 四项验收结果 |
| `status` | `passed`、`patched`、`audited`、`patch_rejected`、`regeneration_limit` 或 `audit_fallback` |
| `structure_preserved` | 修正后是否保留原有标题和列表数量 |
| `regeneration_count` | 当前已重新生成的次数 |

其他相关状态：

| 字段 | 位置 | 说明 |
|---|---|---|
| `final_response` | `TutorState` | 当前待验收或最终交付的回答 |
| `_content_regeneration_count` | `context` | 实际重写次数，每轮开始时重置为 0 |
| `knowledge_responder_regeneration` | `context` | 重写模型的输出、错误类型和 `correction_issues` |
| `_last_agent` | `context` | 最近执行的智能体名称 |
| `_last_output` | `context` | 最近执行节点的结构化输出 |

### 附属文件及具体作用

| 文件 | 具体内容 |
|---|---|
| `backend/app/services/agents/content_corrector.py` | 内容矫正智能体注册入口，继承 `BaseAgent` 并加载 `content_corrector.yaml` |
| `backend/config/prompts/content_corrector.yaml` | 四项验收规则、PASS/PATCH/REGENERATE 边界、输入输出 Schema 和模型参数 |
| `backend/app/graph/nodes/content_correction.py` | 调用智能体、校验 PATCH 范围、限制重写次数并写入过程字段 |
| `backend/app/graph/nodes/content_regeneration.py` | 把问题列表交回 `knowledge_responder` 重写；失败时保留上一次回答 |
| `backend/tests/test_content_correction.py` | PASS 原文保持、PATCH 局部限制、REGENERATE 单次回环和异常兜底测试 |

## 3. LangGraph 编排

```text
START
  ↓
safety_check（执行 safety_gate）
  ├─ REJECT → assemble_response → END
  ├─ GUIDE  → assemble_response → 前端显示学科/知识点选项 → 下一轮重新进入 safety_check
  └─ PASS
       ├─ 普通 PASS → emotion_preprocess → decide
       └─ GUIDE 已完成选择 → execute_stage（直接进入 teaching）
                                  ↓
                    execute_stage / execute_agent
                                  ↓
                  correct_content（执行 content_correction）
                    ├─ PASS/PATCH → assemble_response → END
                    └─ REGENERATE → regenerate_content
                                             ↓
                                      correct_content
                                             ↓
                                      assemble_response → END
```

### 安全监测路由字段

| 字段 | 说明 |
|---|---|
| `safety_branch` | 当前 `PASS/REJECT/GUIDE` 分支 |
| `safety_action` | 兼容旧调用方，值与 `safety_branch` 相同 |
| `safety_context` | 分类、转化和两阶段选择状态 |
| `safety_response` | REJECT/GUIDE 的直接回复 |
| `safety_blocked_response` | 兼容旧 checkpoint 的回复别名 |
| `context.pending_safety_guide` | 等待学生继续选择的完整 GUIDE 状态 |
| `requires_user_input` | 当前图是否需要等待学生输入 |
| `interrupt_reason` | 预留的中断原因字段；当前安全交互未单独写值 |

GUIDE 第一阶段和第二阶段都通过 `assemble_response` 结束当前轮。学生提交选择后重新进入 `safety_check`；最终选择完成时写入 `resolved_from_guide=true`，用 `HumanMessage(safe_query)` 替换当前教学输入，并直接路由到 `execute_stage`。

### 前端 GUIDE 字段

后端在完成事件中输出 `safetyGuide`：

| 字段 | 类型 | 说明 |
|---|---|---|
| `safeQuery` | `string` | 当前阶段的安全引导问题 |
| `options` | `string[]` | 最多 3 个选择项 |
| `recommendedOption` | `string` | 推荐项，缺失时使用第一项 |

前端将该对象保存到 `pendingSafetyGuide`，点击选项后把选项文本作为下一条学生消息发送，从而恢复下一轮 LangGraph 执行。

### LangGraph 接线文件

| 文件 | 接线内容 |
|---|---|
| `backend/app/graph/state.py` | 定义安全分支、回复、上下文和最终回答字段 |
| `backend/app/graph/builder.py` | 注册节点，配置安全分支、内容矫正和单次重写的条件边 |
| `backend/app/graph/engine.py` | 初始化每轮状态，输出安全与内容矫正过程事件 |
| `backend/app/graph/nodes/safety_gate.py` | 运行安全管线，保存/恢复两阶段 GUIDE 状态，替换安全教学问题 |
| `backend/app/graph/nodes/stage_executor.py` | 执行原教育 Stage，并把教学回答写入 `final_response` |
| `backend/app/graph/nodes/agent_node.py` | free-composition 模式执行智能体队列并写入最终内容 |
| `backend/app/graph/nodes/response_assembler.py` | 组装 REJECT、GUIDE、PASS、PATCH 和异常兜底的最终回复 |
| `backend/app/services/agents/__init__.py` | 注册 `content_corrector` 智能体 |
| `backend/app/services/chat_service.py` | 把 GUIDE 状态转换为前端 `safetyGuide` 契约 |
| `frontend/src/types/index.ts` | 定义 `SafetyGuide` 和完成事件类型 |
| `frontend/src/services/chat.service.ts` | 兼容解析 camelCase/snake_case GUIDE 字段 |
| `frontend/src/stores/chatStore.ts` | 保存和清除 `pendingSafetyGuide` |
| `frontend/src/components/chat/ChatInput.tsx` | 渲染学科与知识点按钮并发送选择结果 |
| `frontend/src/components/chat/AgentInteractionLog.tsx` | 展示安全监测和内容矫正过程字段 |
| `frontend/src/data/agentConfigs.ts` | 增加两个智能体的前端名称和说明 |
