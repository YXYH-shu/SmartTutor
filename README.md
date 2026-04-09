# Smart Tutor v2 — 智能教育导师系统

基于 **LangGraph** 的多智能体教育系统，后端 FastAPI + SQLite，前端 React + TypeScript。

## 系统架构

### LangGraph 图拓扑

```
START → safety_check → emotion_preprocess → decide ─┬─ continue_stage → execute_stage → assemble_response → END
                                                      ├─ switch_stage   → execute_stage → assemble_response → END
                                                      ├─ free_composition → execute_agent ↻ → assemble_response → END
                                                      └─ finish → assemble_response → END
```

- **emotion_preprocess**: 每轮必执行情感分析，不经过决策模型
- **decide**: LLM 决策中枢，识别用户意图并路由到对应 workflow/stage
- **execute_stage**: 按顺序执行当前 stage 的所有 agent（内部 agent → 输出 agent）
- **execute_agent**: free_composition 模式下逐个执行自定义 agent 序列
- **assemble_response**: 组装最终回复（仅在 final_response 为空时 fallback）

### 8 个教育智能体

| 智能体 | 职责 |
|--------|------|
| safety_monitor | 内容安全检测与过滤 |
| emotion_analyzer | 学生情感状态分析（每次自动执行） |
| cognitive_diagnosis | 知识点掌握度诊断 |
| resource_recommender | 学习资源推荐 |
| content_polisher | 教学内容润色与校准 |
| empathy_generator | 共情回复生成 |
| learning_path | 个性化学习路径规划 |
| study_buddy | 学伴匹配 |

### 4 个预定义 Workflow

| Workflow | 说明 | Stage 划分 |
|----------|------|-----------|
| onboarding | 新用户引导 | welcome → diagnosis_and_plan |
| adaptive_learning | 自适应学习（默认） | teaching → comprehension_check |
| collaborative_learning | 协作学习 | buddy_matching → collaboration_guide |
| review_assessment | 复习评估 | weak_spot_review → path_adjustment |

每个 stage = 一轮执行完毕需要生成输出的最小单位，内部操作合并到同一 stage。

## 项目结构

```
smart_tutor/
├── backend/                  # FastAPI 后端
│   ├── alembic/              # 数据库迁移
│   ├── app/
│   │   ├── config.py         # Pydantic-settings 配置
│   │   ├── database.py       # 异步 SQLAlchemy 引擎 & session
│   │   ├── main.py           # FastAPI 入口
│   │   ├── api/v1/           # REST API 路由 (auth, users, conversations, chat)
│   │   ├── middleware/       # 错误处理、日志、限流
│   │   ├── models/           # ORM 模型
│   │   ├── schemas/          # Pydantic 请求/响应模型
│   │   ├── graph/            # LangGraph 编排引擎
│   │   │   ├── state.py      # TutorState 定义
│   │   │   ├── decision_engine.py  # LLM 决策路由
│   │   │   ├── builder.py    # StateGraph 构建
│   │   │   ├── engine.py     # TutorGraphEngine 封装
│   │   │   └── nodes/        # 图节点实现
│   │   │       ├── safety_gate.py
│   │   │       ├── emotion_preprocess.py  # 情感分析（每次自动执行）
│   │   │       ├── decision_node.py
│   │   │       ├── stage_executor.py
│   │   │       ├── agent_node.py
│   │   │       └── response_assembler.py
│   │   └── services/         # 业务逻辑 + 智能体
│   │       ├── llm_client.py          # 统一 LLM 调用封装
│   │       ├── auth_service.py        # 认证服务
│   │       ├── chat_service.py        # 聊天 + SSE 流式
│   │       ├── conversation_service.py
│   │       └── agents/               # 8 个教育智能体
│   ├── config/
│   │   ├── app.yaml          # 默认配置文件
│   │   ├── workflows.yaml    # 预定义教育流程
│   │   └── prompts/          # 提示词文件（每个智能体一个 YAML）
│   ├── smart_tutor.db        # SQLite 数据库（本地开发）
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/                 # React 前端
│   ├── src/
│   │   ├── components/       # UI 组件
│   │   │   ├── chat/         # ChatContainer, MessageBubble, ChatInput
│   │   │   ├── layout/       # MainLayout, Sidebar, Header
│   │   │   ├── common/       # 通用组件
│   │   │   └── ui/           # 基础 UI 组件
│   │   ├── pages/            # Login, Register, Dashboard
│   │   ├── stores/           # Zustand 状态管理
│   │   ├── services/         # API 调用封装
│   │   └── types/            # TypeScript 类型定义
│   ├── Dockerfile
│   └── nginx.conf
├── docker-compose.yml
└── README.md
```

## 快速启动

### 本地开发（零依赖，SQLite）

**后端：**

```bash
conda create -n tutor python=3.11 -y
conda activate tutor
cd backend && pip install -r requirements.txt

# 数据库迁移（SQLite，无需额外安装数据库）
alembic upgrade head

# 启动后端
uvicorn app.main:app --reload --port 8000
```

**前端（Node 18+）：**

```bash
cd frontend && npm install
npm run dev    # http://localhost:5173
```

前端开发时需要后端运行在 `localhost:8000`（Vite 已配置代理）。

### 环境变量

在 `backend/.env` 中配置（本地开发已有默认值）：

| 环境变量 | 说明 | 默认值 |
|---------|------|--------|
| `SMART_TUTOR_DATABASE__URL` | 数据库连接串 | `sqlite+aiosqlite:///./smart_tutor.db` |
| `SMART_TUTOR_LLM__PROVIDER` | LLM 提供者 | `glm` |
| `SMART_TUTOR_LLM__BASE_URL` | LLM API 地址 | 智谱 GLM API |
| `SMART_TUTOR_LLM__API_KEY` | API Key | — |
| `SMART_TUTOR_LLM__MODEL_NAME` | 模型名 | `glm-5` |
| `SMART_TUTOR_APP__DEBUG` | 调试模式 | `true` |
| `SMART_TUTOR_APP__SECRET_KEY` | JWT 密钥 | — |
| `SMART_TUTOR_LANGGRAPH__CHECKPOINT_TYPE` | 检查点类型 | `memory` |

### Docker 部署（生产环境，MySQL）

```bash
docker-compose up -d

# 查看日志
docker-compose logs -f
```

服务启动后：
- 前端地址：`http://localhost:3000`
- API 地址：`http://localhost:8000`
- API 文档：`http://localhost:8000/docs`
- MySQL：`localhost:3306`（用户 `tutor` / 密码 `tutor123`）

### 查看数据库

```bash
# 进入 SQLite 命令行
cd backend && sqlite3 smart_tutor.db

# 常用命令
.tables                          # 列出所有表
.schema user_profiles            # 查看表结构
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

## 开发阶段

| 阶段 | 内容 | 状态 |
|------|------|------|
| 1 | 基础架构搭建 | ✅ |
| 2 | 智能体 + LLM 封装 | ✅ |
| 3 | LangGraph 核心引擎 | ✅ |
| 4 | API 路由 + 认证 | ✅ |
| 5 | React 前端 | ✅ |
| 6 | 图拓扑重构（emotion_preprocess 固定节点、stage 合并） | ✅ |
