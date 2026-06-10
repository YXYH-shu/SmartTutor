# kt-runtime-skill

这是 SmartTutor 内嵌的 KT/REKT 学情分析 Skill，供 `../chat-agent` 子服务调用。

REKT 推理代码、数据和 checkpoint 已内化到本目录，不再依赖外部 REKT 项目目录。路径应始终基于本 Skill 目录或 SmartTutor 根目录计算，不要写本机绝对路径。

## 1. 关键入口

从本目录运行：

```bash
conda run -n kt python scripts/run_kt.py --student-id 42 --history-context "闭合回路、电流断开、摩擦力、植物阳光"
```

从 SmartTutor 根目录运行：

```bash
conda run -n kt python services/kt-runtime-skill/scripts/run_kt.py --student-id 42 --history-context "闭合回路、电流断开、摩擦力、植物阳光"
```

快速检查推理链路，不调用自然语言分析：

```bash
conda run -n kt python services/kt-runtime-skill/scripts/run_kt.py --student-id 42 --targets 1 --history-context "闭合回路" --disable-analysis-report
```

## 2. 内置资源

```text
scripts/kt_runtime/rekt_engine/      # 内化后的 REKT 推理代码
assets/rekt/dataset/                 # REKT 数据
assets/rekt/checkpoint/rekt.pt       # REKT checkpoint
config/runtime.toml                  # 推理运行配置
```

默认请求 `cuda:0`，如果 CUDA 不可用，会自动 fallback 到 CPU。

## 3. ChatAgent 调用方式

ChatAgent 通过 `services/chat-agent/config/skills.toml` 发现本 Skill：

```toml
path = "../kt-runtime-skill"
```

调用时主要读取 `scripts/run_kt.py` 的 JSON 输出，其中重点字段是：

```text
llm_analysis.report_markdown
llm_analysis.agent_revision_task
llm_analysis.mastery_table
llm_analysis.selected_knowledge_points
```

最终用户报告应保留四节结构：

```text
## 1. 主题判定
## 2. 知识点集合
## 3. 学情分析结果
## 4. 诊断知识点明细
```

## 4. 验证

从本目录运行：

```bash
conda run -n kt python -m unittest discover -s tests
```

从 SmartTutor 根目录运行集成检查：

```bash
bash scripts/kt-topic4/check_kt_integration.sh
```

## 5. 版本管理约束

- 不提交 `.env`。
- 不提交 `.git/`。
- 不提交 `Agents.md`、`AGENTS.md`、运行日志和缓存。
- `SKILL.md` 是 Skill 的正式运行契约，需要保留。
