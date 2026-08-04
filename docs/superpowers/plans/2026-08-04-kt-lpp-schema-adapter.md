# KT/LPP Schema Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不修改 SmartTutor 预定义工作流的情况下，让认知诊断和路径规划 Agent 分别消费真实 KT/LPP Runtime，并输出原项目可直接消费的兼容字段。

**Architecture:** 保留现有 LangGraph、安全和情感固定节点。`cognitive_diagnosis` 内部通过 KT 适配器获得真实掌握度，`learning_path` 内部通过 LPP 适配器获得固定 P1～P5；两个 Agent 均在 LLM 返回后用 Runtime 事实覆盖不可改写字段。学生编号按显式输入、用户画像映射、配置默认值 `43` 的优先级解析。

**Tech Stack:** Python 3.11、FastAPI、LangGraph、Pydantic Settings、PyYAML、pytest/pytest-asyncio、React/TypeScript、REKT/PyTorch、LPP Runtime。

## Global Constraints

- 不修改 `backend/config/workflows.yaml`。
- 不修改安全策略与情感分析的图执行顺序。
- KT 掌握度和 LPP P1～P5 只能来自 Runtime，LLM 不得伪造或改写。
- 当前阶段默认 REKT/LPP 学生编号为字符串 `"43"`。
- 后端 canonical 路径字段为 `learning_path`，同时返回前端兼容别名 `stages`。
- 未经用户明确允许，不执行 `git commit` 或远程推送。

---

### Task 1: Student ID and Runtime Settings

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/app/services/kt_integration.py`
- Modify: `backend/.env.example`
- Modify: `docker-compose.yml`
- Test: `backend/tests/test_kt_lpp_schema_adapter.py`

**Interfaces:**
- Produces: `resolve_kt_student_id(input_data: dict[str, Any], context: dict[str, Any] | None = None) -> str | None`
- Produces: `settings.kt.demo_student_id == "43"`
- Produces: `settings.lpp` with `enabled`, `skill_path`, `timeout_seconds`, `history_length`, and `seed`

- [ ] **Step 1: Write failing resolver/config tests**

```python
def test_student_id_resolution_priority(monkeypatch):
    monkeypatch.setattr(settings.kt, "demo_student_id", "43")
    assert resolve_kt_student_id({"student_id": "9"}, {}) == "9"
    assert resolve_kt_student_id(
        {"user_profile": {"preferences": {"kt_student_id": "17"}}}, {}
    ) == "17"
    assert resolve_kt_student_id({}, {}) == "43"
```

- [ ] **Step 2: Verify RED**

Run: `conda run -n kt pytest backend/tests/test_kt_lpp_schema_adapter.py::test_student_id_resolution_priority -q`

Expected: FAIL because `resolve_kt_student_id` and the default `43` setting do not exist.

- [ ] **Step 3: Implement settings and resolver**

```python
class KTSettings(BaseSettings):
    mode: Literal["off", "integrated", "standalone"] = "integrated"
    skill_path: str = "services/kt-runtime-skill"
    device: str = "cuda:0"
    default_targets: str = ""
    demo_student_id: str = "43"
    timeout_seconds: int = 180

class LPPSettings(BaseSettings):
    enabled: bool = True
    skill_path: str = "services/lpp-skill"
    timeout_seconds: int = 600
    history_length: int = 10
    seed: int = 42
```

Resolver priority: explicit `kt_student_id`/`student_id`, message pattern `学生43`, profile preference, configured `43`.

- [ ] **Step 4: Verify GREEN**

Run: `conda run -n kt pytest backend/tests/test_kt_lpp_schema_adapter.py::test_student_id_resolution_priority -q`

Expected: PASS.

---

### Task 2: KT Output Contract

**Files:**
- Modify: `backend/app/services/kt_integration.py`
- Modify: `backend/app/services/agents/cognitive_diagnosis.py`
- Modify: `backend/config/prompts/cognitive_diagnosis.yaml`
- Test: `backend/tests/test_kt_lpp_schema_adapter.py`

**Interfaces:**
- Consumes: `resolve_kt_student_id(input_data, context)`
- Produces: normalized `knowledge_states`, `mastery_rates`, `weak_points`, `diagnosis_source`, `kt_metrics`, and `kt_model_info`
- Produces: original required diagnosis fields even when Runtime is unavailable

- [ ] **Step 1: Write failing KT normalization and merge tests**

```python
def test_kt_normalization_supplies_original_schema_fields():
    result = _normalize_kt_output(RAW_KT_FIXTURE)
    state = result["knowledge_states"][0]
    assert state["skill_id"] == "17"
    assert state["type"] in {"概念", "规律", "方法", "价值"}
    assert state["mastery_percent"] == "25.0%"
    assert state["mastery_label"] == "较低"

@pytest.mark.asyncio
async def test_cognitive_agent_runtime_facts_override_llm(monkeypatch):
    runtime = {
        "knowledge_states": [{
            "skill_id": "17", "skill_name": "物质分类", "type": "概念",
            "mastery_percent": "25.0%", "mastery_rate": 0.25,
            "mastery_label": "较低", "status": "weak",
        }],
        "mastery_rates": {"17": 0.25},
        "weak_points": [{"skill_id": "17", "skill_name": "物质分类"}],
        "metrics": {}, "model_info": {},
    }
    llm = MagicMock()
    llm.chat_completion = AsyncMock(return_value={
        "content": {
            "topic_analysis": "分析", "knowledge_states": [{"skill_id": "fake"}],
            "cognitive_attribution": {"root_causes": []}, "weak_points": [],
            "diagnosis_summary": "总结", "recommended_actions": [],
            "knowledge_graph": {"nodes": [], "edges": []},
        },
        "usage": {},
    })
    llm.validate_json_response = AsyncMock(side_effect=lambda content, schema: content)
    agent = CognitiveDiagnosisAgent(llm=llm)
    agent._run_kt_diagnosis = AsyncMock(return_value=runtime)
    agent._log_execution = AsyncMock()
    agent.post_process = AsyncMock()
    monkeypatch.setattr(settings.kt, "mode", "integrated")

    output = (await agent.execute({"current_message": "分析学情"}, {}))["output"]

    assert output["mastery_rates"] == {"17": 0.25}
    assert output["knowledge_states"][0]["skill_id"] == "17"
```

- [ ] **Step 2: Verify RED**

Run: `conda run -n kt pytest backend/tests/test_kt_lpp_schema_adapter.py -k 'kt_normalization or runtime_facts' -q`

Expected: FAIL because normalized rows lack all original schema fields and ID resolution still follows old UUID fallback.

- [ ] **Step 3: Implement minimal KT mapping**

Add `mastery_label`, schema-safe `type`, evidence and source fields during normalization. Update `CognitiveDiagnosisAgent.execute()` to resolve student `43`, call Runtime in integrated mode, return a schema-compatible unavailable result on failure, and reapply Runtime facts after the LLM call.

- [ ] **Step 4: Verify GREEN and existing regression tests**

Run:

```bash
conda run -n kt pytest backend/tests/test_kt_lpp_schema_adapter.py -k 'kt_' -q
conda run -n kt pytest backend/tests/test_agents.py backend/tests/test_done_event_aggregation.py -q
```

Expected: PASS.

---

### Task 3: LPP Runtime Migration

**Files:**
- Create: `services/lpp-skill/**` from `feat/lpp-integration`
- Create: `backend/app/services/lpp_integration.py`
- Test: `services/lpp-skill/tests/test_target_selection.py`
- Test: `services/lpp-skill/tests/test_regression_vs_dsmoea.py`
- Test: `backend/tests/test_kt_lpp_schema_adapter.py`

**Interfaces:**
- Produces: `LppRuntimeOutput(data: dict[str, Any], raw_json: str)`
- Produces: `run_lpp_for_student(student_id: str, *, target_question_id: int | None = None, preferred_skill_ids: list[int] | None = None) -> LppRuntimeOutput | None`
- Produces: `validate_lpp_result(result: dict[str, Any]) -> None`

- [ ] **Step 1: Add failing adapter contract tests**

```python
def test_lpp_contract_requires_exactly_five_ordered_questions():
    validate_lpp_result(valid_runtime_fixture())
    broken = valid_runtime_fixture()
    broken["recommendation"]["questions"].pop()
    with pytest.raises(ValueError, match="exactly 5"):
        validate_lpp_result(broken)
```

- [ ] **Step 2: Verify RED**

Run: `conda run -n kt pytest backend/tests/test_kt_lpp_schema_adapter.py -k lpp_contract -q`

Expected: import/contract failure because the LPP integration module is absent.

- [ ] **Step 3: Migrate only Runtime assets and implement the adapter**

Bring the self-contained `services/lpp-skill` tree from `feat/lpp-integration`. Reuse its subprocess boundary and validation, excluding report-specific ChatAgent integration. The adapter must set `KT_RUNTIME_SKILL_ROOT`, enforce timeout, require `status == "ok"`, `message == "recommendations_ready"`, five questions, and orders `1..5`.

- [ ] **Step 4: Verify GREEN and Runtime tests**

Run:

```bash
conda run -n kt pytest backend/tests/test_kt_lpp_schema_adapter.py -k lpp_contract -q
conda run -n kt pytest services/lpp-skill/tests/test_target_selection.py -q
```

Expected: PASS.

---

### Task 4: Learning Path Original-Field Adapter

**Files:**
- Modify: `backend/app/services/agents/learning_path.py`
- Modify: `backend/config/prompts/learning_path.yaml`
- Modify: `frontend/src/data/agentConfigs.ts`
- Test: `backend/tests/test_kt_lpp_schema_adapter.py`
- Test: `frontend/tests/agent-config-contract.test.mjs`

**Interfaces:**
- Consumes: `LppRuntimeOutput`
- Produces: `planning_rationale`, `learning_path`, `stages`, `total_estimated_time`, `estimated_completion`, `adaptive_rules`, `main_path_sequence`, `optional_branch`, `milestones`, `path_adjustment_triggers`, `recommended_questions`, and `lpp_source`

- [ ] **Step 1: Write failing Agent merge tests**

```python
@pytest.mark.asyncio
async def test_learning_path_preserves_runtime_questions_and_aliases(monkeypatch):
    result = await configured_agent.execute({"current_message": "规划学习路径"}, {})
    output = result["output"]
    assert output["learning_path"] == output["stages"]
    assert output["total_estimated_time"] == output["estimated_completion"]
    assert [q["order"] for q in output["recommended_questions"]] == [1, 2, 3, 4, 5]
    assert output["lpp_source"] == "lpp_runtime"
```

- [ ] **Step 2: Verify RED**

Run: `conda run -n kt pytest backend/tests/test_kt_lpp_schema_adapter.py -k learning_path -q`

Expected: FAIL because `LearningPathAgent` still delegates entirely to `BaseAgent`.

- [ ] **Step 3: Implement mapping and protected merge**

Map P1～P5 deterministically to five schema-compatible stages, one stage per recommended question. Use Runtime data for question content and sequence. Let LLM fill explanation fields, then overwrite `recommended_questions`, `learning_path`/`stages`, source markers and time aliases from deterministic adapter output.

- [ ] **Step 4: Verify GREEN and frontend contract**

Run:

```bash
conda run -n kt pytest backend/tests/test_kt_lpp_schema_adapter.py -k learning_path -q
node --test frontend/tests/agent-config-contract.test.mjs
```

Expected: PASS.

---

### Task 5: End-to-End Verification

**Files:**
- Modify: `scripts/kt-topic4/check_kt_integration.sh`
- Modify: `README.md` or `课题4.1学情分析启动说明.md`
- Modify: `docs/superpowers/specs/2026-08-04-kt-lpp-schema-adapter-design.md`

**Interfaces:**
- Verifies the unchanged workflow consumes the new Agent outputs through existing context keys.

- [ ] **Step 1: Run focused backend suite**

```bash
conda run -n kt pytest \
  backend/tests/test_kt_lpp_schema_adapter.py \
  backend/tests/test_agents.py \
  backend/tests/test_done_event_aggregation.py -q
```

- [ ] **Step 2: Run Runtime tests**

```bash
conda run -n kt pytest services/lpp-skill/tests/test_target_selection.py -q
conda run -n kt python -m unittest discover -s services/kt-runtime-skill/tests
```

- [ ] **Step 3: Run static and frontend checks**

```bash
bash scripts/kt-topic4/check_kt_integration.sh
cd frontend && npm run build
git diff --check
```

- [ ] **Step 4: Review scope and report**

Confirm `backend/config/workflows.yaml` is unchanged, the worktree contains no generated database/build artifacts, and no commits were created during implementation. Report modified files, verification results and remaining risks to the user.
