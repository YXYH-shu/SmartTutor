# SmartTutor — 多智能体自适应教育系统

基于 **LangGraph** 的多智能体教育平台，通过 9 个协同智能体和 5 阶段安全管线实现认知诊断、资源推荐、学伴匹配、路径规划等功能。后端 FastAPI + SQLAlchemy async，前端 React + TypeScript。

## 系统架构

### LangGraph 图拓扑

```
START → safety_check ─┬─ [SAFE/TRANSFORM] → emotion_preprocess → decide ─┬─ continue_stage → execute_stage → assemble_response → END
                      └─ [BLOCK/REFERRAL] → assemble_response → END       ├─ switch_stage   → execute_stage → assemble_response → END
                                                                              ├─ free_composition → execute_agent ↻ → assemble_response → END
                                                                              └─ finish → assemble_response → END
```

- **safety_check**: 5 阶段安全管线（风险感知→意图识别→价值评估→教育引导→问题转化）。危险内容直接拦截（HARD_BLOCK/SOFT_BLOCK/REFERRAL），需转化的内容改写后继续流转（TRANSFORM），安全内容放行（SAFE）
- **emotion_preprocess**: 每轮必执行情感分析（emotion_analyzer），结果写入 state 供后续节点使用
- **decide**: LLM 决策中枢，识别用户意图并路由到对应 workflow/stage
- **execute_stage**: 按顺序执行当前 stage 的所有 agent，最后一个 agent 的输出作为用户可见回复
- **execute_agent**: free_composition 模式下逐个执行自定义 agent 序列
- **assemble_response**: 组装最终回复（仅在 final_response 为空时 fallback 调用 empathy_generator）

### 9 个教育智能体

| 智能体 | 职责 | 版本 |
|--------|------|------|
| safety_monitor | 内容安全检测与过滤（独立 agent，被安全管线内部调用） | v1.0 |
| emotion_analyzer | 学生情感状态分析（每轮自动执行） | v1.0 |
| cognitive_diagnosis | 知识掌握度评估 + 认知归因（15-25 知识点 + 知识图谱 + 安全维度） | v3.0 |
| learning_path | 基于诊断结果的个性化学习路径规划（3-5 阶段 + 风险纠偏） | v3.0 |
| resource_recommender | 自然语言风格资源推荐（具体资源 + 关联知识点 + 学习建议） | v3.0 |
| study_buddy | 自然语言风格学伴推荐（具体学伴 + 适配原因 + 陪伴感） | v3.0 |
| knowledge_responder | 知识问答与内容响应 | v1.0 |
| content_polisher | 教学内容矫正与润色 | v1.0 |
| empathy_generator | 共情回复生成与心理支持 | v1.0 |

> **LLM 模拟说明**：当前所有智能体通过 LLM 调用模拟功能，保持与真实智能体相同的输入输出接口。真实智能体（DKT、推荐工具链、匹配算法）将在后续迭代中接入。

### 5 阶段安全管线

safety_check 节点内部运行 5 阶段管线，根据结果做条件路由：

```
Stage 1 风险感知 ─── 未检测到风险 → SAFE（放行）
        │
        检测到风险 → 分类为 A/B/C/D1/D2/D3
        │
        ├── C 类（心理危机信号）→ REFERRAL（关怀文本，短出到 assemble_response）
        │
Stage 2 意图识别 ─── 科学好奇 / 情绪表达 / 边界试探 / 明确恶意
        │
Stage 3 价值评估 ─── 决定动作：TRANSFORM / SOFT_BLOCK / HARD_BLOCK / REFERRAL
        │
        ├── SOFT_BLOCK / HARD_BLOCK → 短出到 assemble_response
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

### 4 个预定义 Workflow

| Workflow | 说明 | Stage 划分 |
|----------|------|-----------|
| onboarding | 新用户引导，建立画像和基线 | welcome → diagnosis_and_plan |
| adaptive_learning | 自适应学习（默认主流程） | teaching → comprehension_check |
| collaborative_learning | 学伴推荐，协作学习 | buddy_matching → collaboration_guide |
| review_assessment | 阶段复习与测试 | weak_spot_review → path_adjustment |

每个 stage = 一轮执行完毕需要生成输出的最小单位。内部诊断操作合并到同一 stage，最后一个 agent 产出用户可见内容。

## 数据库

### 表结构（19 张表）

**核心业务表（7 张）：**

| 表名 | 说明 |
|------|------|
| users | 用户账号 |
| user_profiles | 用户画像（知识图谱、学习风格、掌握度、薄弱点、学段） |
| conversations | 对话会话（含 workflow_type、current_stage 状态） |
| messages | 聊天消息 |
| message_feedbacks | 消息反馈 |
| agent_execution_logs | 智能体执行日志 |
| checkpoints | LangGraph 状态检查点 |

**知识图谱与资源（2 张）：**

| 表名 | 说明 |
|------|------|
| knowledge_points | 知识点（含前置关系、父节点、学段、认知层次、难度、嵌入向量） |
| learning_resources | 学习资源（视频/文章/练习，含知识覆盖度、满分值、嵌入向量） |

**学习者交互（3 张）：**

| 表名 | 说明 |
|------|------|
| learner_resource_interactions | 学习者-资源交互（学习时长、评分、情感、结果类型/详情/正确性/得分） |
| learner_knowledge_interactions | 学习者-知识点交互（掌握度评分、诊断算法版本） |
| learner_learner_relations | 学习者关系（多维相似度，学伴推荐用） |

**推荐记录（2 张）：**

| 表名 | 说明 |
|------|------|
| resource_recommendations | 资源推荐记录（候选集、排序结果、反馈） |
| buddy_recommendations | 学伴推荐记录（匹配分、策略、反馈） |

**概念、技能与关系（5 张）：**

| 表名 | 说明 |
|------|------|
| concepts | 概念实体（知识点的自然语言解释） |
| skills | 技能实体（可训练、可测量的能力） |
| resource_knowledge | 资源-知识点多对多关联 |
| concept_knowledge | 概念-知识点多对多关联 |
| skill_knowledge | 技能-知识点多对多关联 |

**知识图谱关系（1 张）：**

| 表名 | 说明 |
|------|------|
| knowledge_knowledge | 知识点间前置/后续关系（prerequisite/related/contains/applies_to/extends_to/constrained_by） |

## 项目结构

```
SmartTutor/
├── backend/                    # FastAPI 后端
│   ├── alembic/                # 数据库迁移
│   │   └── versions/
│   │       ├── 0001_initial_schema.py   # 初始建表
│   │       └── 0002_add_relation_tables.py  # 新增 6 张关系表 + 现有表字段补充
│   ├── app/
│   │   ├── config.py           # Pydantic-settings 配置
│   │   ├── database.py         # 异步 SQLAlchemy 引擎
│   │   ├── main.py             # FastAPI 入口
│   │   ├── api/v1/             # REST API 路由
│   │   │   ├── auth.py         # 注册/登录/刷新Token
│   │   │   ├── users.py        # 用户管理
│   │   │   ├── conversations.py # 对话管理
│   │   │   └── chat.py         # 聊天 + SSE 流式
│   │   ├── middleware/         # 错误处理、日志、限流
│   │   ├── models/             # ORM 模型（19 个模型，18 个文件）
│   │   ├── graph/              # LangGraph 编排引擎
│   │   │   ├── state.py        # TutorState 定义（含安全管线状态字段）
│   │   │   ├── decision_engine.py  # LLM 决策路由
│   │   │   ├── builder.py      # StateGraph 构建（含安全条件路由）
│   │   │   ├── engine.py       # TutorGraphEngine 封装
│   │   │   └── nodes/          # 图节点实现
│   │   │       ├── safety_gate.py       # 安全管线入口
│   │   │       ├── emotion_preprocess.py
│   │   │       ├── decision_node.py
│   │   │       ├── stage_executor.py    # 含 safety_context 传递
│   │   │       ├── agent_node.py
│   │   │       └── response_assembler.py # 含安全拦截回复处理
│   │   └── services/           # 业务逻辑 + 智能体
│   │       ├── llm_client.py           # 统一 LLM 调用封装
│   │       ├── safety_pipeline.py      # 5 阶段安全管线编排器
│   │       ├── auth_service.py
│   │       ├── chat_service.py
│   │       ├── conversation_service.py
│   │       └── agents/                 # 9 个教育智能体
│   │           ├── base_agent.py       # 基类（配置加载→Jinja2渲染→LLM调用→JSON校验→日志持久化）
│   │           ├── cognitive_diagnosis.py  # 含 post_process 更新 UserProfile
│   │           ├── learning_path.py
│   │           ├── resource_recommender.py
│   │           ├── study_buddy.py
│   │           ├── knowledge_responder.py
│   │           ├── content_polisher.py
│   │           ├── empathy_generator.py
│   │           ├── emotion_analyzer.py
│   │           └── safety_monitor.py
│   ├── config/
│   │   ├── workflows.yaml      # 4个预定义 Workflow + Stage 定义
│   │   └── prompts/            # 提示词文件（15 个 YAML）
│   │       ├── cognitive_diagnosis.yaml   # v3.0
│   │       ├── learning_path.yaml         # v3.0
│   │       ├── resource_recommender.yaml  # v3.0
│   │       ├── study_buddy.yaml           # v3.0
│   │       ├── decision.yaml              # v2.0（含安全路由指引）
│   │       ├── emotion_analyzer.yaml
│   │       ├── content_polisher.yaml
│   │       ├── empathy_generator.yaml
│   │       ├── knowledge_responder.yaml
│   │       ├── safety_monitor.yaml        # 原始安全提示词（备份）
│   │       ├── safety_stage1_risk.yaml    # 风险感知
│   │       ├── safety_stage2_intent.yaml  # 意图识别
│   │       ├── safety_stage3_value.yaml   # 价值评估
│   │       ├── safety_stage4_education.yaml # 教育引导
│   │       └── safety_stage5_transform.yaml # 问题转化
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/                   # React + TypeScript + Zustand
│   ├── src/
│   │   ├── components/         # UI 组件
│   │   │   ├── chat/           # ChatContainer, MessageBubble, ChatInput
│   │   │   └── layout/         # MainLayout, Sidebar, Header
│   │   ├── pages/              # Login, Register, Dashboard
│   │   ├── stores/             # Zustand 状态管理
│   │   ├── services/           # API 调用封装
│   │   └── types/              # TypeScript 类型定义
│   ├── Dockerfile
│   └── nginx.conf
├── docker-compose.yml
├── 文档/                       # 课题文档（提示词规范、数据表设计）
└── README.md
```

## 快速启动

### 1. 后端

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

### 2. 前端

```bash
cd frontend && npm install
CLC    # http://localhost:5173
```

前端开发时需要后端运行在 `localhost:8000`（Vite 已配置代理）。

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

### 查看数据库

```bash
cd backend && sqlite3 smart_tutor.db

.tables                          # 列出所有表
.schema knowledge_points         # 查看表结构
SELECT * FROM users LIMIT 5;     # 查询数据
.mode column && .headers on      # 格式化输出
.quit                            # 退出
```

## 数据库迁移

```bash
cd backend

# 生成迁移脚本（自动检测模型变更）
alembic revision --autogenerate -m "describe your change"

# 执行迁移
alembic upgrade head

# 回退一步
alembic downgrade -1
```

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
