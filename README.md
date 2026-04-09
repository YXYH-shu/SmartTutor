# SmartTutor — 多智能体自适应教育系统

基于 **LangGraph** 的多智能体教育平台，通过 8 个协同智能体实现认知诊断、资源推荐、学伴匹配、路径规划等功能。后端 FastAPI + SQLite，前端 React + TypeScript。

## 系统架构

### LangGraph 图拓扑

```
START → safety_check → emotion_preprocess → decide ─┬─ continue_stage → execute_stage → assemble_response → END
                                                      ├─ switch_stage   → execute_stage → assemble_response → END
                                                      ├─ free_composition → execute_agent ↻ → assemble_response → END
                                                      └─ finish → assemble_response → END
```

- **safety_check**: 内容安全检测，有害内容直接拦截
- **emotion_preprocess**: 每轮必执行情感分析（emotion_analyzer），不经过决策模型，结果写入 state 供后续节点使用
- **decide**: LLM 决策中枢，识别用户意图并路由到对应 workflow/stage
- **execute_stage**: 按顺序执行当前 stage 的所有 agent，最后一个 agent 的输出作为用户可见回复
- **execute_agent**: free_composition 模式下逐个执行自定义 agent 序列
- **assemble_response**: 组装最终回复（仅在 final_response 为空时 fallback 调用 empathy_generator）

### 8 个教育智能体

| 智能体 | 职责 | 当前模式 |
|--------|------|----------|
| safety_monitor | 内容安全检测与过滤 | LLM 模拟 |
| emotion_analyzer | 学生情感状态分析（每轮自动执行） | LLM 模拟 |
| cognitive_diagnosis | 知识掌握度评估 + 认知归因（模拟 Knowledge Tracing） | LLM 模拟 → 未来接入 DKT |
| learning_path | 基于诊断结果的个性化学习路径规划 | LLM 模拟 → 未来接入自适应算法 |
| resource_recommender | 多阶段推荐（Planning→Execution→Summary→Reflection） | LLM 模拟 → 未来接入工具链 |
| study_buddy | 多维度学伴匹配（知识互补/水平/风格/情感） | LLM 模拟 → 未来接入匹配算法 |
| content_polisher | 教学内容矫正与润色 | LLM 模拟 |
| empathy_generator | 共情回复生成与心理支持 | LLM 模拟 |

> **LLM 模拟说明**：当前所有智能体通过 LLM 调用模拟功能，保持与真实智能体相同的输入输出接口。真实智能体（DKT、推荐工具链、匹配算法）将在后续迭代中接入。

### 4 个预定义 Workflow

| Workflow | 说明 | Stage 划分 |
|----------|------|-----------|
| onboarding | 新用户引导，建立画像和基线 | welcome → diagnosis_and_plan |
| adaptive_learning | 自适应学习（默认主流程） | teaching → comprehension_check |
| collaborative_learning | 学伴推荐，协作学习 | buddy_matching → collaboration_guide |
| review_assessment | 阶段复习与测试 | weak_spot_review → path_adjustment |

每个 stage = 一轮执行完毕需要生成输出的最小单位。内部诊断操作合并到同一 stage，最后一个 agent 产出用户可见内容。

## 数据库

### 表结构（15 张表）

**核心业务表：**

| 表名 | 说明 |
|------|------|
| users | 用户账号 |
| user_profiles | 用户画像（知识图谱、学习风格、掌握度、薄弱点） |
| conversations | 对话会话（含 workflow_type、current_stage 状态） |
| messages | 聊天消息 |
| message_feedbacks | 消息反馈 |
| agent_execution_logs | 智能体执行日志 |
| checkpoints | LangGraph 状态检查点 |

**知识图谱与资源：**

| 表名 | 说明 |
|------|------|
| knowledge_points | 知识点（含前置关系、父节点、难度、嵌入向量） |
| learning_resources | 学习资源（视频/文章/练习，含知识覆盖度、嵌入向量） |

**学习者交互：**

| 表名 | 说明 |
|------|------|
| learner_resource_interactions | 学习者-资源交互（学习时长、评分、情感） |
| learner_knowledge_interactions | 学习者-知识点交互（掌握度评分，认知诊断用） |
| learner_learner_relations | 学习者关系（多维相似度，学伴推荐用） |

**推荐记录：**

| 表名 | 说明 |
|------|------|
| resource_recommendations | 资源推荐记录（候选集、排序结果、反馈） |
| buddy_recommendations | 学伴推荐记录（匹配分、策略、反馈） |

## 项目结构

```
SmartTutor/
├── backend/                    # FastAPI 后端
│   ├── alembic/                # 数据库迁移
│   │   └── versions/
│   │       └── 0001_initial_schema.py   # 初始建表（15张表）
│   ├── app/
│   │   ├── config.py           # Pydantic-settings 配置
│   │   ├── database.py         # 异步 SQLAlchemy 引擎 (aiosqlite)
│   │   ├── main.py             # FastAPI 入口
│   │   ├── api/v1/             # REST API 路由
│   │   │   ├── auth.py         # 注册/登录/刷新Token
│   │   │   ├── users.py        # 用户管理
│   │   │   ├── conversations.py # 对话管理
│   │   │   └── chat.py         # 聊天 + SSE 流式
│   │   ├── middleware/         # 错误处理、日志、限流
│   │   ├── models/             # ORM 模型（13个模型文件）
│   │   ├── schemas/            # Pydantic 请求/响应模型
│   │   ├── graph/              # LangGraph 编排引擎
│   │   │   ├── state.py        # TutorState 定义
│   │   │   ├── decision_engine.py  # LLM 决策路由
│   │   │   ├── builder.py      # StateGraph 构建
│   │   │   ├── engine.py       # TutorGraphEngine 封装
│   │   │   └── nodes/          # 图节点实现
│   │   │       ├── safety_gate.py
│   │   │       ├── emotion_preprocess.py
│   │   │       ├── decision_node.py
│   │   │       ├── stage_executor.py
│   │   │       ├── agent_node.py
│   │   │       └── response_assembler.py
│   │   └── services/           # 业务逻辑 + 智能体
│   │       ├── llm_client.py           # 统一 LLM 调用封装
│   │       ├── auth_service.py
│   │       ├── chat_service.py
│   │       ├── conversation_service.py
│   │       └── agents/                 # 8 个教育智能体
│   │           ├── base_agent.py       # 基类（配置加载→Jinja2渲染→LLM调用→JSON校验→日志持久化）
│   │           ├── cognitive_diagnosis.py  # 含 post_process 更新 UserProfile
│   │           ├── learning_path.py
│   │           ├── resource_recommender.py
│   │           ├── study_buddy.py
│   │           ├── content_polisher.py
│   │           ├── empathy_generator.py
│   │           ├── emotion_analyzer.py
│   │           └── safety_monitor.py
│   ├── config/
│   │   ├── workflows.yaml      # 4个预定义 Workflow + Stage 定义
│   │   └── prompts/            # 提示词文件（每个智能体一个 YAML）
│   │       ├── cognitive_diagnosis.yaml   # v2.0: knowledge_states + cognitive_attribution
│   │       ├── learning_path.yaml         # v2.0: path_stages + adjustment_triggers
│   │       ├── resource_recommender.yaml  # v2.0: planning→resources→reflection Pipeline
│   │       ├── study_buddy.yaml           # v2.0: matching_plan + buddies + group_suggestion
│   │       ├── decision.yaml              # v2.0: 决策中枢提示词
│   │       ├── emotion_analyzer.yaml
│   │       ├── content_polisher.yaml
│   │       ├── empathy_generator.yaml
│   │       └── safety_monitor.yaml
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
npm run dev    # http://localhost:5173
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
| 7 | 数据表整合（15 张表、Alembic 迁移） | Done |
| 8 | 智能体提示词 v2.0（对齐协作者规范） | Done |
| 9 | 状态流转修复（checkpoint 恢复、switch_stage 推断、数据传递） | Done |
| 10 | 真实智能体接入（DKT、推荐工具链、匹配算法） | Planned |

## 技术栈

| 层级 | 技术 |
|------|------|
| LLM 编排 | LangGraph + LangChain |
| 后端框架 | FastAPI + Uvicorn |
| 数据库 | SQLite (aiosqlite) / MySQL (aiomysql) |
| ORM | SQLAlchemy 2.0 (async) |
| 迁移 | Alembic |
| 配置 | pydantic-settings |
| 认证 | JWT (python-jose) |
| 前端 | React 18 + TypeScript + Vite |
| 状态管理 | Zustand |
| 样式 | TailwindCSS |
| 部署 | Docker + docker-compose |
