# KT/LPP Prompt Compaction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改变 KT/LPP 算法逻辑和最终 Runtime 字段的前提下，把传给 LLM 的重复全量数据压缩为有界摘要，并将认知诊断输出上限提高到 32768。

**Architecture:** Runtime 继续完整运行并保留完整结果。新增纯投影函数分别生成认知诊断和学习路径 Prompt 上下文；Agent 只把投影结果交给 LLM，随后继续用完整 Runtime 事实执行 `finalize_output()` 覆盖。

**Tech Stack:** Python 3.11、pytest、Jinja2、PyYAML、KT、LPP Runtime。

## Global Constraints

- 不修改 `services/kt-runtime-skill` 的推理与数据代码。
- 不修改 `services/lpp-skill` 的目标题选择、遗传搜索、候选池与固定五题逻辑。
- 不修改 `backend/config/workflows.yaml`。
- 认知诊断 Prompt 最多接收 18 个 KT 状态；学习路径 Prompt 最多接收 10 个诊断状态。
- 最终 Agent 输出继续保留完整 Runtime 事实。
- `cognitive_diagnosis.llm_config.max_tokens` 必须等于 `32768`。
- 未经用户明确允许，不执行提交或推送。

---

### Task 1: KT Prompt Projection

**Files:**
- Modify: `backend/app/services/kt_integration.py`
- Modify: `backend/app/services/agents/cognitive_diagnosis.py`
- Modify: `backend/config/prompts/cognitive_diagnosis.yaml`
- Test: `backend/tests/test_kt_lpp_schema_adapter.py`

**Interfaces:**
- Produces: `build_kt_prompt_context(kt_result: dict[str, Any]) -> dict[str, Any]`
- Consumes: complete normalized KT result
- Preserves: complete `_kt_result` used by `finalize_output()`

- [ ] **Step 1: Write failing projection and model-limit tests**

Create 25 weak, 10 developing and 5 mastered fixture states. Assert the projected `priority_states` contains 10 weak, 5 developing and 3 mastered states, is deduplicated, and excludes full `mastery_rates`/`weak_points` copies. Assert YAML `max_tokens == 32768`.

- [ ] **Step 2: Verify RED**

Run: `conda run -n kt pytest backend/tests/test_kt_lpp_schema_adapter.py -k 'prompt_context or token_limit' -q`

Expected: FAIL because `build_kt_prompt_context` is absent and the current limit is 4028.

- [ ] **Step 3: Implement the bounded projection**

Implement a pure selector in `kt_integration.py`. Update `_merge_kt_with_llm()` to add only `kt_context`, remove the three full Prompt fields, update the Jinja template, and set `max_tokens: 32768`. Do not change `_kt_result` or `finalize_output()`.

- [ ] **Step 4: Verify GREEN**

Run: `conda run -n kt pytest backend/tests/test_kt_lpp_schema_adapter.py -k 'prompt_context or cognitive_agent or token_limit' -q`

Expected: PASS and the existing full-runtime override assertion remains green.

---

### Task 2: Learning Path Diagnosis Projection

**Files:**
- Modify: `backend/app/services/lpp_integration.py`
- Modify: `backend/app/services/agents/learning_path.py`
- Test: `backend/tests/test_kt_lpp_schema_adapter.py`

**Interfaces:**
- Produces: `build_diagnosis_prompt_context(diagnosis: dict[str, Any], max_states: int = 10) -> dict[str, Any]`
- Preserves: `skill_priorities_from_diagnosis(diagnosis)` consuming the complete diagnosis before projection
- Preserves: complete `LppRuntimeOutput` and P1～P5 merge

- [ ] **Step 1: Write the failing bounded-diagnosis test**

Create a diagnosis with more than 10 states. Assert the Prompt projection contains at most 10 lowest-mastery states plus summary, actions and counts, without the full knowledge graph or complete mastery map.

- [ ] **Step 2: Verify RED**

Run: `conda run -n kt pytest backend/tests/test_kt_lpp_schema_adapter.py -k diagnosis_prompt_context -q`

Expected: FAIL because the projection helper is absent.

- [ ] **Step 3: Implement projection after algorithm inputs are derived**

Keep `skill_priorities_from_diagnosis()` before the LPP call. Immediately before `BaseAgent.execute()`, replace only `enriched_input["diagnosis_result"]` with the bounded projection. Do not alter the LPP arguments or Runtime result.

- [ ] **Step 4: Verify GREEN**

Run: `conda run -n kt pytest backend/tests/test_kt_lpp_schema_adapter.py -k 'diagnosis_prompt_context or learning_path' -q`

Expected: PASS and the existing P1～P5 preservation test remains green.

---

### Task 3: Regression and Runtime Verification

**Files:**
- Verify only: `backend/config/workflows.yaml`
- Verify only: `services/kt-runtime-skill/**`
- Verify only: `services/lpp-skill/**`

- [ ] **Step 1: Run backend tests**

Run: `conda run -n kt pytest backend/tests -q`

- [ ] **Step 2: Run Runtime tests and student 43 smoke checks**

Run the KT student 43 adapter and LPP student 43 adapter, confirming 334 KT states and exactly five ordered LPP questions.

- [ ] **Step 3: Run static checks**

Run `git diff --check` and confirm `git diff --exit-code HEAD -- backend/config/workflows.yaml`.

- [ ] **Step 4: Report without committing**

Report Prompt bounds, Runtime counts, tests and any remaining risk. Do not commit or push.
