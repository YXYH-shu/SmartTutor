# KT/LPP Output Budget and Prompt Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将认知诊断和路径规划的输出预算统一为 16384，阻止完整用户画像与 LPP 诊断数据进入路径解释 Prompt，并在 JSON 模式下安全处理 reasoning-only 响应。

**Architecture:** KT 与 LPP Runtime 继续消费完整数据并保持算法输出。`LearningPathAgent.enrich_input()` 作为 LLM 边界，把完整输入投影为有界白名单；完整 Runtime 只保存在执行上下文中供最终事实覆盖。`LLMClient` 在 JSON content 为空时关闭 Thinking 重试，不解析自然语言 reasoning。

**Tech Stack:** Python 3.11、pytest、Jinja2、PyYAML、OpenAI-compatible API、React/TypeScript。

## Global Constraints

- 不修改 `services/kt-runtime-skill` 或 `services/lpp-skill` 的算法代码。
- 不修改 `backend/config/workflows.yaml`。
- `cognitive_diagnosis` 与 `learning_path` 的 `max_tokens` 都必须为 `16384`。
- 完整认知诊断必须先供 LPP Runtime 使用，压缩只能发生在 Runtime 返回之后。
- 最终 P1～P5 必须继续由完整 Runtime 覆盖。
- 未经用户明确允许，不执行提交或推送。

---

### Task 1: Output Budget Contract

**Files:**
- Modify: `backend/config/prompts/cognitive_diagnosis.yaml`
- Modify: `backend/config/prompts/learning_path.yaml`
- Modify: `frontend/src/data/agentConfigs.ts`
- Test: `backend/tests/test_kt_lpp_schema_adapter.py`

**Interfaces:**
- Consumes: Agent YAML `llm_config`
- Produces: both feature Agents invoking the model with `max_tokens=16384`

- [x] Add failing tests asserting both Agent runtime configs equal `16384`.
- [x] Run the focused tests and confirm they fail against `32768` and `4028`.
- [x] Change both YAML values and the two frontend static overview values to `16384`.
- [x] Run the focused tests and confirm they pass.

### Task 2: Bounded LPP Prompt Projection

**Files:**
- Modify: `backend/app/services/lpp_integration.py`
- Modify: `backend/app/services/agents/learning_path.py`
- Test: `backend/tests/test_kt_lpp_schema_adapter.py`

**Interfaces:**
- Produces: `build_learning_profile_prompt_context(profile: dict[str, Any]) -> dict[str, Any]`
- Produces: `build_lpp_prompt_context(result: dict[str, Any]) -> dict[str, Any]`
- Produces: `build_relevant_knowledge_graph_prompt_context(graph: dict[str, Any], skill_ids: set[str]) -> dict[str, Any]`
- Preserves: full diagnosis for `skill_priorities_from_diagnosis()` and full `LppRuntimeOutput` in `_lpp_runtime`

- [x] Add a failing Agent-boundary test with sentinel values inside full profile weak points, graph nodes, Runtime diagnostics and related questions.
- [x] Assert the rendered Prompt excludes every sentinel, contains exactly five ordered questions, at most ten diagnosis states, and only relevant graph nodes.
- [x] Run the focused test and confirm it fails because `LearningPathAgent` currently rehydrates and renders full profile/runtime data.
- [x] Implement pure projection helpers and override `LearningPathAgent.enrich_input()` to apply them after DB enrichment.
- [x] Keep `execute()` algorithm inputs complete and place the complete Runtime only in `_lpp_runtime`.
- [x] Run focused schema-adapter tests and confirm P1～P5 preservation remains green.

### Task 3: JSON Reasoning-only Retry

**Files:**
- Modify: `backend/app/services/llm_client.py`
- Create: `backend/tests/test_llm_client.py`

**Interfaces:**
- Consumes: OpenAI-compatible response with empty `message.content` and non-empty `message.reasoning_content`
- Produces: one retry with `extra_body.thinking.type = "disabled"` in JSON mode
- Preserves: reasoning fallback for non-JSON text requests

- [x] Add a failing async test whose first response is reasoning-only and whose second response contains valid JSON.
- [x] Confirm the current implementation fails by parsing the first reasoning string as JSON.
- [x] Change `chat_completion()` so JSON mode retries once with Thinking disabled instead of parsing reasoning.
- [x] Run the focused client test and confirm the second response is returned as a JSON object.

### Task 4: Regression and Runtime Verification

**Files:**
- Verify only: `backend/config/workflows.yaml`
- Verify only: `services/kt-runtime-skill/**`
- Verify only: `services/lpp-skill/**`

- [x] Run all backend tests and both Runtime test suites.
- [x] Render a real student 43 KT/LPP Prompt and record its token/character reduction.
- [x] Confirm real student 43 still yields 334 KT states and exactly five ordered LPP questions.
- [x] Run the frontend build, YAML parsing, `git diff --check`, workflow diff and algorithm-file checks.
- [x] Restart affected services and verify backend health and frontend HTTP 200.
- [x] Report results without committing or pushing.
