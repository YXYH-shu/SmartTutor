# ChatAgent 子服务

这是 SmartTutor 内嵌的学情分析对话子服务。它提供独立 Web 页面，负责维护学情分析对话、调用 `../kt-runtime-skill`，并把 KT 诊断结果组织成可展示的 Markdown 报告。

SmartTutor 前端通过 iframe 打开该服务：

```text
/dashboard/kt-diagnosis -> http://127.0.0.1:8910/?embed=1
```

嵌入模式下，页面左侧“测试场景”和右侧“执行过程”默认收起，用户可以在页面内展开。

## 1. 目录关系

```text
SmartTutor/
  services/
    chat-agent/
    kt-runtime-skill/
```

`config/skills.toml` 中的 Skill 路径应保持为：

```toml
path = "../kt-runtime-skill"
skill_sources = [".."]
```

不要把路径改成本机绝对路径。

## 2. 配置

不要提交 `.env`。本目录的 `.env` 已被 SmartTutor 根目录 `.gitignore` 忽略。

复制示例文件：

```bash
cp services/chat-agent/.env.example services/chat-agent/.env
```

填写真实模型配置：

```env
CHATAGENT_LLM_BASE_URL=https://your-openai-compatible-endpoint/v1
CHATAGENT_LLM_API_KEY=replace-with-your-api-key
CHATAGENT_LLM_MODEL=replace-with-your-model-name
CHATAGENT_LLM_TIMEOUT=120
CHATAGENT_LLM_TEMPERATURE=0
CHATAGENT_DEEPAGENT_ENABLED=true
```

## 3. 启动

推荐从 SmartTutor 根目录用统一脚本启动：

```bash
bash scripts/kt-topic4/start_chat_agent.sh
```

脚本默认使用 `kt` conda 环境。需要换环境名时：

```bash
KT_CONDA_ENV=your-env bash scripts/kt-topic4/start_chat_agent.sh
```

需要换端口时：

```bash
CHATAGENT_PORT=8911 bash scripts/kt-topic4/start_chat_agent.sh
```

端口变更后，要同步修改 `frontend/.env`：

```env
VITE_KT_CHATAGENT_URL=http://127.0.0.1:8911/
```

也可以从本目录直接启动：

```bash
cd services/chat-agent
conda run -n kt uvicorn chat_agent.server:app --host 127.0.0.1 --port 8910
```

## 4. 验证

健康检查：

```bash
curl --noproxy '*' http://127.0.0.1:8910/api/health
```

页面检查：

```bash
curl --noproxy '*' http://127.0.0.1:8910/ | grep leftPanelToggle
```

单测：

```bash
cd services/chat-agent
conda run -n kt python -m pytest tests/test_skill_markdown_executor.py tests/test_deep_agent_runtime_generic.py tests/test_web_contract.py
```

完整集成检查可在 SmartTutor 根目录运行：

```bash
bash scripts/kt-topic4/check_kt_integration.sh
```

## 5. 版本管理约束

- 不提交 `.env`。
- 不提交 `.git/`。
- 不提交 `Agents.md`、`AGENTS.md`、运行日志、缓存和 `.runtime/`。
- `SKILL.md` 属于被调用 Skill 的运行契约，不是工作记录文件。
