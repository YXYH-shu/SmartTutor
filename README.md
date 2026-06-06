# SmartTutor — 多智能体自适应教育系统

SmartTutor 是一个基于 LangGraph 的多智能体教育平台。系统通过多个协同智能体实现**认知诊断、情感分析、学习路径规划、资源推荐、学伴匹配、知识问答**等功能，配合 5 阶段安全管线保障学生使用安全。后端采用 FastAPI + SQLAlchemy 异步架构，前端为 React + TypeScript SPA。

> **当前状态说明**：系统中所有智能体目前通过大模型（LLM）调用来模拟功能实现，保持了与真实智能体相同的输入输出接口规范。后续迭代中，可以在不改变接口的前提下，将模拟实现替换为真实的智能体服务（如 DKT 认知追踪模型、推荐系统工具链、学伴匹配算法等）。

---

## 目录

- [系统设计概览](#系统设计概览)
- [智能体详解](#智能体详解)
- [图编排与流转机制](#图编排与流转机制)
- [5 阶段安全管线](#5-阶段安全管线)
- [预定义 Workflow](#预定义-workflow)
- [前端设计](#前端设计)
- [数据库设计](#数据库设计)
- [项目目录结构](#项目目录结构)
- [快速启动](#快速启动)
- [开发进度](#开发进度)
- [技术栈](#技术栈)

---

## 系统设计概览

SmartTutor 的核心思路是**将教育场景拆解为多个专职智能体，通过 LangGraph 状态图编排它们之间的协作流转**。

整体架构分三层：

```
┌─────────────────────────────────────────────────────┐
│                    前端 (React SPA)                   │
│          登录 / 对话 / 智能体信息面板 / 侧边栏         │
├─────────────────────────────────────────────────────┤
│               API 层 (FastAPI + JWT)                  │
│          认证 / 对话管理 / SSE 流式推送                 │
├─────────────────────────────────────────────────────┤
│              LangGraph 编排引擎                       │
│    ┌─────────┐  ┌──────────┐  ┌───────────────┐     │
│    │ 安全管线  │→│ 情感分析  │→│ 决策路由       │     │
│    └─────────┘  └──────────┘  └──────┬────────┘     │
│                                      ↓               │
│                          ┌───────────────────┐       │
│                          │  Stage 执行器      │       │
│                          │  (按序调度智能体)   │       │
│                          └─────────┬─────────┘       │
│                                    ↓                  │
│                          ┌───────────────────┐       │
│                          │  回复组装器        │       │
│                          │  (最终输出给学生)   │       │
│                          └───────────────────┘       │
├─────────────────────────────────────────────────────┤
│               数据层 (SQLAlchemy + MySQL/SQLite)      │
│     用户 / 对话 / 知识图谱 / 资源 / 交互记录 / 推荐记录  │
└─────────────────────────────────────────────────────┘
```

每轮对话的处理流程：

1. **安全检测** — 5 阶段安全管线评估输入内容，危险内容拦截或转化，安全内容放行
2. **情感分析** — 自动识别学生情绪状态，结果供后续所有智能体参考
3. **决策路由** — LLM 判断当前意图，路由到对应的 Workflow / Stage
4. **智能体调度** — 按 Stage 定义顺序依次调用多个智能体，前一个的输出作为后一个的输入
5. **回复组装** — 提取最终内容返回给学生

---

## 智能体详解

系统共有 **8 个核心教育智能体** + **1 个安全监测智能体**（安全管线内部使用）。所有智能体继承自统一的 `BaseAgent` 基类，遵循相同的处理管线：**YAML 配置加载 → Jinja2 模板渲染 → LLM 调用 → JSON 输出校验 → 执行日志持久化**。

### 8 个核心教育智能体

#### 1. EmotionAnalyzerAgent — 情感分析智能体

- **职责**：分析学生的情感状态，输出情绪名称、强度（0-1）、趋势（improving/stable/declining）、学习意图、建议回应语气
- **运行方式**：**每轮对话自动执行**（通过固定节点 `emotion_preprocess`），不受决策引擎路由控制
- **输出流向**：结果写入 `state["context"]["emotion_analyzer"]`，供所有后续智能体读取
- **参数**：temperature=0.4（低创造性，保证情感判断稳定性）

#### 2. CognitiveDiagnosisAgent — 认知诊断智能体 (v3.0)

- **职责**：知识掌握度评估 + 认知归因。输出 15-25 个知识点的掌握百分比、认知归因（根本原因分析），同时生成知识图谱（含 6 种关系类型）和薄弱点列表
- **特殊行为**：唯一拥有自定义 `post_process()` 方法的智能体。执行后自动更新 UserProfile 中的知识图谱（合并掌握度）、薄弱点和最后诊断时间
- **输出流向**：结果通过 `context["cognitive_diagnosis"]` 展平为 `diagnosis_result`、`mastery_rates`、`knowledge_graph` 传递给下游智能体
- **参数**：temperature=0.3，启用 thinking 模式（深度推理）

#### 3. LearningPathAgent — 学习路径规划智能体 (v3.0)

- **职责**：基于认知诊断结果规划 3-5 阶段个性化学习路径，包含技能点、检查点、预期成果和风险纠偏机制
- **输入依赖**：需要 `diagnosis_result` 和 `knowledge_graph`（来自认知诊断智能体）
- **输出流向**：结果通过 `context["learning_path"]` 传递给下游的知识问答和共情回复智能体
- **参数**：temperature=0.5，启用 thinking 模式

#### 4. ResourceRecommenderAgent — 资源推荐智能体 (v3.0)

- **职责**：个性化学习资源推荐。当前通过 LLM 模拟多工具推荐 Pipeline（召回 + 排序），输出具体资源名称、关联知识点和学习建议
- **输入依赖**：需要 `diagnosis_result`（来自认知诊断智能体）
- **输出流向**：结果通过 `context["resource_recommender"]` 传递给知识问答智能体作为 `resource_list`
- **参数**：temperature=0.5

#### 5. StudyBuddyAgent — 学伴推荐智能体 (v3.0)

- **职责**：学伴匹配推荐。当前通过 LLM 模拟多维度匹配（知识互补、水平相似、风格互补、情感匹配），输出具体学伴信息和适配原因
- **输入依赖**：需要 `knowledge_graph` 和 `topic`
- **输出流向**：结果通过 `context["study_buddy"]` 传递给知识问答智能体作为 `buddy_info`
- **参数**：temperature=0.5

#### 6. KnowledgeResponderAgent — 知识问答智能体

- **职责**：核心内容生成智能体。根据当前 Stage 和可用上下文（诊断结果、资源列表、学伴信息、学习计划）生成自然语言回复
- **运行方式**：几乎所有 Workflow 的所有 Stage 中都会出现，通常是 Stage 内最后或倒数第二个执行，其输出直接成为学生可见的回复
- **参数**：temperature=0.7（所有智能体中最高，保证回复自然多样）

#### 7. ContentPolisherAgent — 内容润色智能体

- **职责**：教学内容矫正与润色。检查科学准确性、语言清晰度、角色一致性（教师人设）、情感基调
- **输入依赖**：接收前一个智能体的输出作为 `content`
- **输出字段**：`polished_content` + `corrections_made`
- **参数**：temperature=0.4

#### 8. EmpathyGeneratorAgent — 共情回复智能体

- **职责**：将原始教学内容融入共情属性，使学生感到被理解和支持，同时不扭曲原始回复中的事实和信息
- **输入依赖**：`raw_response`（前一个智能体的输出）、`emotion_state`、`user_profile`
- **输出字段**：`empathetic_response`、`psychological_techniques`、`teacher_persona`
- **运行方式**：通常作为 Stage 内最后一个智能体，也作为 `response_assembler` 节点的回退机制
- **参数**：temperature=0.6

### SafetyMonitorAgent — 安全监测智能体

- **职责**：独立的安全检测代理，评估内容风险等级（low/medium/high），转化危险文本，提供教育引导说明
- **运行方式**：作为安全管线的一部分，不直接参与 Workflow Stage 的智能体调度序列

### 智能体间数据流

```
                    ┌──────────────────┐
                    │ EmotionAnalyzer  │ ──→ emotion_state (全员可读)
                    └──────────────────┘
                              ↓
                    ┌──────────────────┐
              ┌────→│CognitiveDiagnosis│────→ diagnosis_result
              │     └──────────────────┘      mastery_rates
              │              ↓                 knowledge_graph
              │     ┌──────────────────┐              │
              │     │  LearningPath    │←─────────────┘
              │     └──────────────────┘
              │              ↓ learning_plan
              │     ┌──────────────────┐
              │     │ResourceRecommender│←── diagnosis_result
              │     └──────────────────┘
              │              ↓ resource_list       ┌──────────────┐
              │     ┌──────────────────┐           │ StudyBuddy   │
              │     │KnowledgeResponder│←──────────└──────────────┘
              │     └──────────────────┘  ← buddy_info
              │              ↓
              │     ┌──────────────────┐
              │     │ ContentPolisher  │←── content
              │     └──────────────────┘
              │              ↓ polished_content
              │     ┌──────────────────┐
              └────→│ EmpathyGenerator │←── emotion_state
                    └──────────────────┘
                              ↓ empathetic_response
                        (最终回复)
```

智能体间通过 `state["context"]` 字典传递数据。Stage 执行器在调用每个智能体前，会自动从 context 中展平关键字段作为输入。前一个智能体的完整输出同时以自身名称存储在 context 中（如 `ctx["cognitive_diagnosis"]`），供后续智能体直接访问。

---

## 图编排与流转机制

### LangGraph 图拓扑

```
START
  → safety_check（5 阶段安全管线）
      ├─ [HARD_BLOCK / SOFT_BLOCK / REFERRAL] → assemble_response → END
      └─ [SAFE / TRANSFORM] → emotion_preprocess（情感分析，固定执行）
          → decide（LLM 决策路由）
              ├─ continue_stage → execute_stage → assemble_response → END
              ├─ switch_stage   → execute_stage → assemble_response → END
              ├─ free_composition → execute_agent ↻ → assemble_response → END
              └─ finish → assemble_response → END
```

### 节点说明

| 节点 | 类型 | 说明 |
|------|------|------|
| `safety_gate` | 固定节点 | 运行 5 阶段安全管线，每轮自动执行 |
| `emotion_preprocess` | 固定节点 | 运行情感分析智能体，每轮自动执行 |
| `decide` | 决策节点 | LLM 决策中枢，识别意图并路由到对应 Workflow/Stage |
| `execute_stage` | 执行节点 | 按 `workflows.yaml` 定义的智能体序列顺序执行 |
| `execute_agent` | 执行节点 | free_composition 模式下逐个执行自定义智能体序列 |
| `assemble_response` | 终端节点 | 组装最终回复（仅在 `final_response` 为空时回退调用 empathy_generator） |

### 决策路由动作

| 动作 | 含义 |
|------|------|
| `continue_stage` | 继续当前 Stage 的下一轮执行 |
| `switch_stage` | 切换到当前 Workflow 的下一个 Stage |
| `free_composition` | 自由组合模式，按需选择智能体执行 |
| `finish` | 结束当前 Workflow |

### Workflow 自动流转

`TutorGraphEngine` 实现了 Workflow 间的自动切换：

- `onboarding` 完成后自动切换到 `adaptive_learning`
- `review_assessment` 完成后自动切换到 `adaptive_learning`
- 其他 Workflow 完成后保持当前 Workflow

---

## 5 阶段安全管线

安全管线由 `SafetyPipeline` 类实现，使用 5 个独立的 YAML 提示词配置。在每轮对话开始时自动运行。

```
Stage 1 风险感知 ─── 未检测到风险 → SAFE（放行）
        │
        检测到风险 → 分类为 A/B/C/D1/D2/D3
        │
        ├── C 类（心理危机信号）→ REFERRAL（直接关怀文本，短路到回复组装）
        │
Stage 2 意图识别 ─── 科学好奇 / 情绪表达 / 边界试探 / 明确恶意
        │
Stage 3 价值评估 ─── 决定动作：TRANSFORM / SOFT_BLOCK / HARD_BLOCK / REFERRAL
        │
        ├── SOFT_BLOCK / HARD_BLOCK → 短路到回复组装
        │
Stage 4 教育引导 ─── 主题映射 + 核心概念 + 学段适配（仅 TRANSFORM 路径）
        │
Stage 5 问题转化 ─── 语义锚定 + 操作剥离 + 引导嵌入（仅 TRANSFORM 路径）
        │
        → 改写后的教育性内容替代原始输入，继续正常流转
```

| 风险类别 | 说明 | 默认处置 |
|----------|------|----------|
| A | 危险操作（爆炸物、自伤工具等） | TRANSFORM → 教育引导 |
| B | 学段不当内容 | TRANSFORM → 适龄化改写 |
| C | 心理危机信号 | REFERRAL → 直接关怀 |
| D1/D2/D3 | 伦理敏感（偏见、隐私、深度伪造） | TRANSFORM → 伦理教育 |

---

## 预定义 Workflow

| Workflow | 说明 | Stage 划分 |
|----------|------|-----------|
| `onboarding` | 新用户引导，建立画像和基线 | welcome → diagnosis_and_plan |
| `adaptive_learning` | 自适应学习（默认主流程） | teaching → comprehension_check |
| `collaborative_learning` | 学伴推荐，协作学习 | buddy_matching → collaboration_guide |
| `review_assessment` | 阶段复习与测试 | weak_spot_review → path_adjustment |

### 每个 Stage 的智能体调度序列

| Workflow | Stage | 智能体执行顺序 |
|----------|-------|----------------|
| onboarding | welcome | knowledge_responder → empathy_generator |
| | diagnosis_and_plan | cognitive_diagnosis → learning_path → knowledge_responder → content_polisher |
| adaptive_learning | teaching | cognitive_diagnosis → resource_recommender → knowledge_responder → content_polisher → empathy_generator |
| | comprehension_check | cognitive_diagnosis → knowledge_responder → empathy_generator |
| collaborative_learning | buddy_matching | study_buddy → knowledge_responder → content_polisher |
| | collaboration_guide | learning_path → knowledge_responder → empathy_generator |
| review_assessment | weak_spot_review | cognitive_diagnosis → resource_recommender → knowledge_responder → content_polisher → empathy_generator |
| | path_adjustment | learning_path → knowledge_responder → content_polisher |

Stage 是一轮执行完毕需要生成输出的最小单位。最后一个智能体的输出通过 `_extract_text()` 提取为 `final_response`，成为学生可见的回复文本。

---

## 前端设计

前端是一个基于 React 18 + TypeScript 的单页应用（SPA），采用深色主题设计。

### 页面结构

| 路由 | 页面 | 访问控制 |
|------|------|----------|
| `/login` | 登录页 | 未登录可访问 |
| `/register` | 注册页 | 未登录可访问 |
| `/dashboard/chat` | 聊天主页（新对话） | 需登录 |
| `/dashboard/chat/:id` | 聊天主页（指定对话） | 需登录 |

### 界面布局

- **左侧边栏**（可折叠，256px）：品牌 Logo、「新对话」按钮、按日期分组的对话列表（今天/昨天/更早），每条对话支持重命名和删除。底部显示登录用户信息
- **中间区域**：顶部 Header（边栏开关、当前对话标题、智能体面板开关、主题切换）+ 聊天区（欢迎页有 4 个快捷入口：开始诊断、制定计划、找学伴、复习测评）
- **右侧面板**（可折叠，320px）：智能体信息面板。下拉选择 9 个 AI 智能体，展示智能体概览、LLM 配置参数、设计说明和实时分析结果

### 状态管理

| Store | 用途 | 持久化 |
|-------|------|--------|
| `authStore` | JWT 认证状态（用户信息、Token） | localStorage |
| `chatStore` | 对话列表、消息、SSE 流式状态 | 无 |
| `uiStore` | 侧边栏、主题、右侧面板、选中智能体 | theme 持久化到 localStorage |

### SSE 流式通信

聊天消息通过 Server-Sent Events (SSE) 流式推送，协议格式：

| type | 说明 |
|------|------|
| `content` | 文本内容增量 |
| `step` | 处理步骤标签（如智能体名称） |
| `thinking` | 智能体思考过程内容 |
| `done` | 流式完成（含 Workflow 和 Stage 元数据） |
| `error` | 错误信息 |

---

## 数据库设计

系统共 19 张表，支持 MySQL（生产）和 SQLite（开发）。

### 核心业务表（7 张）

| 表名 | 说明 |
|------|------|
| `users` | 用户账号 |
| `user_profiles` | 用户画像（知识图谱、学习风格、掌握度、薄弱点、学段） |
| `conversations` | 对话会话（含 workflow_type、current_stage 状态） |
| `messages` | 聊天消息 |
| `message_feedbacks` | 消息反馈 |
| `agent_execution_logs` | 智能体执行日志 |
| `checkpoints` | LangGraph 状态检查点 |

### 知识图谱与资源（2 张）

| 表名 | 说明 |
|------|------|
| `knowledge_points` | 知识点（含前置关系、父节点、学段、认知层次、难度、嵌入向量） |
| `learning_resources` | 学习资源（视频/文章/练习，含知识覆盖度、满分值、嵌入向量） |

### 学习者交互（3 张）

| 表名 | 说明 |
|------|------|
| `learner_resource_interactions` | 学习者-资源交互（学习时长、评分、情感、结果） |
| `learner_knowledge_interactions` | 学习者-知识点交互（掌握度评分、诊断算法版本） |
| `learner_learner_relations` | 学习者关系（多维相似度，学伴推荐用） |

### 推荐记录（2 张）

| 表名 | 说明 |
|------|------|
| `resource_recommendations` | 资源推荐记录（候选集、排序结果、反馈） |
| `buddy_recommendations` | 学伴推荐记录（匹配分、策略、反馈） |

### 概念、技能与关系（5 张）

| 表名 | 说明 |
|------|------|
| `concepts` | 概念实体（知识点的自然语言解释） |
| `skills` | 技能实体（可训练、可测量的能力） |
| `resource_knowledge` | 资源-知识点多对多关联 |
| `concept_knowledge` | 概念-知识点多对多关联 |
| `skill_knowledge` | 技能-知识点多对多关联 |

### 知识图谱关系（1 张）

| 表名 | 说明 |
|------|------|
| `knowledge_knowledge` | 知识点间前置/后续关系（prerequisite/related/contains/applies_to/extends_to/constrained_by） |

---

## 项目目录结构

```
SmartTutor/
├── backend/                          # 后端服务（FastAPI）
│   ├── Dockerfile                    # 后端 Docker 镜像定义
│   ├── requirements.txt              # Python 依赖
│   ├── alembic.ini                   # Alembic 迁移配置
│   ├── .env / .env.example           # 环境变量
│   ├── alembic/                      # 数据库迁移目录
│   │   ├── env.py                    # Alembic 环境配置
│   │   ├── script.py.mako            # 迁移脚本模板
│   │   └── versions/                 # 迁移版本文件
│   │       ├── 0001_initial_schema.py        # 初始建表（13 张核心表）
│   │       └── 0002_add_relation_tables.py   # 新增 6 张关系表
│   ├── app/                          # 应用主目录
│   │   ├── __init__.py
│   │   ├── config.py                 # Pydantic-settings 配置（数据库/LLM/应用/检查点）
│   │   ├── database.py               # 异步 SQLAlchemy 引擎（支持 SQLite/MySQL）
│   │   ├── main.py                   # FastAPI 入口（CORS/中间件/路由注册/生命周期）
│   │   ├── api/                      # REST API 层
│   │   │   ├── deps.py               # 依赖注入（获取当前用户、数据库会话）
│   │   │   ├── schemas.py            # 通用响应 Schema
│   │   │   └── v1/                   # API v1 路由
│   │   │       ├── auth.py           # 注册/登录/刷新 Token/登出
│   │   │       ├── users.py          # 用户信息查询
│   │   │       ├── conversations.py  # 对话 CRUD（列表/创建/详情/重命名/删除）
│   │   │       └── chat.py           # 聊天（发送/流式推送/重新生成/反馈/历史）
│   │   ├── graph/                    # LangGraph 编排引擎
│   │   │   ├── state.py              # TutorState 定义（含安全/情感/上下文等状态字段）
│   │   │   ├── decision_engine.py    # LLM 决策路由（continue/switch/free/finish）
│   │   │   ├── builder.py            # StateGraph 构建（节点连接+条件路由）
│   │   │   ├── engine.py             # TutorGraphEngine 封装（Workflow 管理+自动流转）
│   │   │   ├── _stream_ctx.py        # SSE 流式上下文管理
│   │   │   └── nodes/               # 图节点实现
│   │   │       ├── safety_gate.py        # 安全管线入口节点
│   │   │       ├── emotion_preprocess.py # 情感分析固定节点
│   │   │       ├── decision_node.py      # LLM 决策节点
│   │   │       ├── stage_executor.py     # Stage 执行器（智能体调度+上下文传递）
│   │   │       ├── agent_node.py         # 单智能体执行节点
│   │   │       └── response_assembler.py # 回复组装节点（含 empathy 回退）
│   │   ├── middleware/               # 中间件
│   │   │   ├── error_handler.py     # 全局异常处理
│   │   │   ├── logging.py           # 请求日志
│   │   │   └── rate_limiter.py      # 限流
│   │   ├── models/                  # ORM 模型（18 个文件，19 个模型）
│   │   ├── schemas/                 # Pydantic 请求/响应 Schema
│   │   └── services/                # 业务逻辑层
│   │       ├── llm_client.py           # 统一 LLM 调用封装（支持 GLM/OpenAI/vLLM）
│   │       ├── safety_pipeline.py      # 5 阶段安全管线编排器
│   │       ├── auth_service.py         # 认证服务（JWT 签发/验证）
│   │       ├── chat_service.py         # 聊天服务（消息处理+流式推送）
│   │       ├── conversation_service.py # 对话管理服务
│   │       ├── trace_logger.py         # 执行链路追踪日志
│   │       └── agents/                 # 智能体实现（9 个）
│   │           ├── base_agent.py           # 基类（配置加载→模板渲染→LLM调用→校验→持久化）
│   │           ├── emotion_analyzer.py     # 情感分析
│   │           ├── cognitive_diagnosis.py  # 认知诊断（含 post_process 更新用户画像）
│   │           ├── learning_path.py        # 学习路径规划
│   │           ├── resource_recommender.py # 资源推荐
│   │           ├── study_buddy.py          # 学伴推荐
│   │           ├── knowledge_responder.py  # 知识问答
│   │           ├── content_polisher.py     # 内容润色
│   │           ├── empathy_generator.py    # 共情回复
│   │           └── safety_monitor.py       # 安全监测
│   ├── config/                       # 配置文件
│   │   ├── app.yaml                  # 应用默认配置（数据库/LLM/应用参数）
│   │   ├── workflows.yaml            # 4 个 Workflow + Stage + 智能体序列定义
│   │   └── prompts/                  # 提示词模板（15 个 YAML）
│   │       ├── cognitive_diagnosis.yaml       # 认知诊断 v3.0
│   │       ├── learning_path.yaml             # 路径规划 v3.0
│   │       ├── resource_recommender.yaml      # 资源推荐 v3.0
│   │       ├── study_buddy.yaml               # 学伴推荐 v3.0
│   │       ├── decision.yaml                  # 决策路由 v2.0
│   │       ├── emotion_analyzer.yaml          # 情感分析
│   │       ├── knowledge_responder.yaml       # 知识问答
│   │       ├── content_polisher.yaml          # 内容润色
│   │       ├── empathy_generator.yaml         # 共情回复
│   │       ├── safety_monitor.yaml            # 安全监测（备份）
│   │       ├── safety_stage1_risk.yaml        # 安全 Stage 1：风险感知
│   │       ├── safety_stage2_intent.yaml      # 安全 Stage 2：意图识别
│   │       ├── safety_stage3_value.yaml       # 安全 Stage 3：价值评估
│   │       ├── safety_stage4_education.yaml   # 安全 Stage 4：教育引导
│   │       └── safety_stage5_transform.yaml   # 安全 Stage 5：问题转化
│   ├── tests/                        # 测试
│   │   ├── test_agents.py            # 智能体单元测试
│   │   └── test_api.http             # API 接口测试（HTTP 文件）
│   └── logs/                         # 运行日志
│       └── trace.log                 # 链路追踪日志
│
├── frontend/                         # 前端服务（React + TypeScript + Vite）
│   ├── Dockerfile                    # 前端 Docker 镜像（多阶段构建：Node 编译 + Nginx 运行）
│   ├── nginx.conf                    # Nginx SPA 路由配置
│   ├── package.json                  # 前端依赖
│   ├── vite.config.ts                # Vite 配置（端口 3000，API 代理到 8000）
│   ├── tsconfig.json                 # TypeScript 配置
│   ├── tailwind.config.js            # Tailwind CSS 配置（自定义蓝色主题色+暗色模式）
│   ├── postcss.config.js             # PostCSS 配置
│   ├── index.html                    # SPA 入口 HTML
│   └── src/                          # 源码目录
│       ├── main.tsx                  # React 入口（createRoot 挂载）
│       ├── App.tsx                   # 根组件（路由定义 + 认证守卫）
│       ├── vite-env.d.ts             # Vite 类型声明
│       ├── types/
│       │   └── index.ts              # 全局 TypeScript 类型定义
│       ├── stores/                   # Zustand 状态管理
│       │   ├── authStore.ts          # 认证状态（JWT Token + 用户信息，localStorage 持久化）
│       │   ├── chatStore.ts          # 聊天状态（消息列表/流式推送/对话管理）
│       │   └── uiStore.ts            # UI 状态（侧边栏/主题/面板/选中智能体）
│       ├── services/                 # API 调用封装
│       │   ├── api.ts                # Axios 实例（JWT 拦截器 + 401 自动刷新）
│       │   ├── auth.service.ts       # 认证 API（登录/注册/刷新/登出）
│       │   ├── chat.service.ts       # 聊天 API（发送/流式/重新生成/反馈/历史）
│       │   └── conversation.service.ts # 对话 API（列表/创建/详情/重命名/删除）
│       ├── pages/                    # 页面组件
│       │   ├── LoginPage.tsx         # 登录页（邮箱+密码表单）
│       │   ├── RegisterPage.tsx      # 注册页（含密码强度指示器）
│       │   └── DashboardPage.tsx     # 聊天主页（加载对话+消息）
│       ├── components/               # UI 组件
│       │   ├── layout/               # 布局组件
│       │   │   ├── MainLayout.tsx    # 主布局（侧边栏+Header+内容区+右侧面板）
│       │   │   ├── Header.tsx        # 顶部栏（侧边栏开关/对话标题/面板开关/主题切换）
│       │   │   └── Sidebar.tsx       # 侧边栏（对话列表按日期分组/新建对话/用户信息）
│       │   ├── chat/                 # 聊天组件
│       │   │   ├── ChatContainer.tsx # 聊天容器（消息列表+输入框+快捷入口）
│       │   │   ├── ChatInput.tsx     # 输入框（自动调整高度/Enter 发送）
│       │   │   ├── MessageBubble.tsx # 消息气泡（Markdown 渲染/代码高亮/思考步骤/反馈按钮）
│       │   │   └── ThinkingView.tsx  # 思考过程展示（可折叠/JSON 树渲染）
│       │   └── agents/               # 智能体信息面板
│       │       ├── AgentInfoPanel.tsx      # 面板容器（智能体选择器+子组件）
│       │       ├── AgentOverview.tsx       # 智能体概览（名称/描述/版本/状态）
│       │       ├── AgentLLMConfig.tsx      # LLM 配置展示（模型/温度/Token 上限）
│       │       └── AgentDesignShowcase.tsx # 设计展示（设计说明/思考管线/分析结果）
│       ├── data/
│       │   └── agentConfigs.ts       # 9 个智能体的硬编码配置（模型/参数/描述/颜色/图标）
│       ├── utils/
│       │   ├── cn.ts                 # CSS 类名合并工具（tailwind-merge + clsx）
│       │   └── jsonTree.tsx          # 递归 JSON 渲染器（中文 key 翻译）
│       └── styles/
│           └── globals.css           # 全局样式（Tailwind 指令/自定义滚动条/动画/毛玻璃效果）
│
├── 文档/                              # 课题文档
│   ├── 安全监测智能体提示词.md         # 安全监测智能体提示词规范
│   ├── 安全监测智能体提示词2.0.docx    # 安全监测智能体提示词 v2.0
│   ├── 数据库表单-课题4.1+4.2.md      # 数据库表结构设计文档
│   ├── 学伴推荐输入输出.md            # 学伴推荐智能体接口规范
│   ├── 资源推荐输入输出.md            # 资源推荐智能体接口规范
│   └── 课题4.1提示工程（学情分析+路径规划）@xza.docx  # 学情分析与路径规划提示工程
│
├── docker-compose.yml                # Docker Compose 编排（MySQL + Backend + Frontend）
└── README.md
```

---

## 快速启动

### 方式一：本地开发

#### 1. 后端

```bash
conda create -n tutor python=3.13 -y
conda activate tutor
cd backend && pip install -r requirements.txt

# 数据库迁移
alembic upgrade head

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入 LLM API Key

# 启动
uvicorn app.main:app --reload --port 8000
```

API 文档：`http://localhost:8000/docs`

#### 2. 前端

```bash
cd frontend && npm install
npm run dev    # http://localhost:5173
```

前端开发时需要后端运行在 `localhost:8000`（Vite 已配置代理）。

### 方式二：Docker 部署

```bash
docker-compose up --build
```

启动后：
- 前端：`http://localhost:3000`
- 后端 API：`http://localhost:8000/docs`
- MySQL：端口 3306

### 环境变量

在 `backend/.env` 中配置：

| 环境变量 | 说明 | 默认值 |
|---------|------|--------|
| `SMART_TUTOR_DATABASE__URL` | 数据库连接串 | `sqlite+aiosqlite:///./smart_tutor.db` |
| `SMART_TUTOR_LLM__PROVIDER` | LLM 提供者 | `glm` |
| `SMART_TUTOR_LLM__BASE_URL` | LLM API 地址 | 智谱 GLM API |
| `SMART_TUTOR_LLM__API_KEY` | API Key（必填） | — |
| `SMART_TUTOR_LLM__MODEL_NAME` | 模型名 | `glm-4-flash` |
| `SMART_TUTOR_APP__DEBUG` | 调试模式 | `true` |
| `SMART_TUTOR_APP__SECRET_KEY` | JWT 密钥 | — |
| `SMART_TUTOR_LANGGRAPH__CHECKPOINT_TYPE` | 检查点类型 | `memory` |

### 数据库操作

```bash
cd backend && sqlite3 smart_tutor.db

.tables                          # 列出所有表
.schema knowledge_points         # 查看表结构
SELECT * FROM users LIMIT 5;     # 查询数据
.mode column && .headers on      # 格式化输出
.quit                            # 退出
```

数据库迁移：

```bash
cd backend

# 生成迁移脚本（自动检测模型变更）
alembic revision --autogenerate -m "describe your change"

# 执行迁移
alembic upgrade head

# 回退一步
alembic downgrade -1
```

---

## 开发进度

| 阶段 | 内容 | 状态 |
|------|------|------|
| 1 | 基础架构搭建 | Done |
| 2 | 智能体 + LLM 封装 | Done |
| 3 | LangGraph 核心引擎 | Done |
| 4 | API 路由 + 认证 | Done |
| 5 | React 前端 | Done |
| 6 | 图拓扑重构（emotion_preprocess 固定节点、stage 合并） | Done |
| 7 | 数据表整合（19 张表、Alembic 迁移） | Done |
| 8 | 智能体提示词 v3.0（对齐课题文档规范） | Done |
| 9 | 状态流转修复（checkpoint 恢复、switch_stage 推断、数据传递） | Done |
| 10 | 5 阶段安全管线（风险感知→意图识别→价值评估→教育引导→问题转化） | Done |
| 11 | 安全条件路由（BLOCK/REFERRAL 短路、TRANSFORM 改写后继续流转） | Done |
| 12 | 概念/技能/知识关系模型（6 张新表 + 关联关系） | Done |
| 13 | 真实智能体接入（DKT、推荐工具链、匹配算法） | Planned |

---

## 技术栈

| 层级 | 技术 |
|------|------|
| LLM 编排 | LangGraph + LangChain |
| 后端框架 | FastAPI + Uvicorn |
| 数据库 | SQLite (aiosqlite) / MySQL (aiomysql) |
| ORM | SQLAlchemy 2.0 (async) |
| 迁移 | Alembic |
| 配置 | pydantic-settings |
| 认证 | JWT (PyJWT) + bcrypt |
| 前端 | React 18 + TypeScript + Vite |
| 状态管理 | Zustand |
| 样式 | TailwindCSS |
| 部署 | Docker + docker-compose |
