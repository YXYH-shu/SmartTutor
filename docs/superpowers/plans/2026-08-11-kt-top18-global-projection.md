# KT Top-18 Global Projection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restrict every new SmartTutor KT diagnosis and its downstream state to the original skill's 18 context-relevant knowledge points.

**Architecture:** Enable the KT skill's analysis report so it yields the authoritative `selected_knowledge_points`. Normalize REKT predictions only for those selected IDs at the KT integration boundary, then replace (rather than merge) a user's persisted knowledge projection.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async ORM, pytest, local `kt-runtime-skill`.

## Global Constraints

- Reuse `kt-runtime-skill` context-relevance selection; do not create a second ranking rule.
- New diagnosis `knowledge_states`, `mastery_rates`, and `weak_points` contain no IDs outside the selected Top-18.
- Do not delete historical execution logs, change unrelated dirty files, or push remotely.

---

### Task 1: Bound the KT normalization at its source

**Files:**
- Modify: `backend/app/services/kt_integration.py:112-183,305-353`
- Modify: `backend/tests/test_kt_lpp_schema_adapter.py`

**Interfaces:**
- Consumes: `{"predictions": [...], "llm_analysis": {"selected_knowledge_points": [{"skill_id": ...}]}}`.
- Produces: `_normalize_kt_output(raw) -> dict[str, Any]` with per-knowledge-point fields limited to selected IDs.

- [ ] **Step 1: Write the failing test**

```python
def test_kt_normalization_keeps_only_skill_selected_top_18():
    predictions = [prediction_for(skill_id) for skill_id in range(1, 335)]
    selected_ids = list(range(101, 119))
    result = kt_integration._normalize_kt_output({
        "predictions": predictions,
        "llm_analysis": {
            "selected_knowledge_points": [{"skill_id": skill_id} for skill_id in selected_ids]
        },
    })

    assert [item["skill_id"] for item in result["knowledge_states"]] == [str(i) for i in selected_ids]
    assert set(result["mastery_rates"]) == {str(i) for i in selected_ids}
    assert {item["skill_id"] for item in result["weak_points"]} <= {str(i) for i in selected_ids}
```

This catches removal of the source filter or accidental fallback to all REKT predictions.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_kt_lpp_schema_adapter.py::test_kt_normalization_keeps_only_skill_selected_top_18 -q`

Expected: FAIL because normalization currently returns all 334 predictions.

- [ ] **Step 3: Write minimal implementation**

```python
def _selected_skill_ids(raw: dict[str, Any]) -> set[str] | None:
    analysis = raw.get("llm_analysis")
    selected = analysis.get("selected_knowledge_points") if isinstance(analysis, dict) else None
    ids = {str(item["skill_id"]) for item in selected or [] if isinstance(item, dict) and item.get("skill_id") is not None}
    return ids or None

selected_ids = _selected_skill_ids(raw)
for pred in predictions:
    skill_id = str(target.get("skill_id", ""))
    if selected_ids is not None and skill_id not in selected_ids:
        continue
```

In `run_kt_for_student`, omit `--disable-analysis-report` so the original skill produces the selected IDs. If selection metadata is absent, cap the fallback at 18 states and warn; never return a complete prediction list.

- [ ] **Step 4: Run focused tests**

Run: `cd backend && pytest tests/test_kt_lpp_schema_adapter.py -q`

Expected: PASS.

### Task 2: Replace persisted knowledge state with the new Top-18 projection

**Files:**
- Modify: `backend/app/services/agents/cognitive_diagnosis.py:184-219`
- Modify: `backend/tests/test_kt_lpp_schema_adapter.py`

**Interfaces:**
- Consumes: normalized diagnosis output containing at most 18 `knowledge_states`.
- Produces: `UserProfile.knowledge_graph` and `UserProfile.weak_points` that contain only the current diagnosis projection.

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_diagnosis_profile_replaces_prior_unselected_knowledge_states(...):
    profile.knowledge_graph = {"old-unselected": 0.1, "17": 0.2}
    output = {"knowledge_states": [{"skill_id": "17", "mastery_rate": 0.25}], "weak_points": []}

    await agent.post_process(output, {"user_id": profile.user_id})

    assert profile.knowledge_graph == {"17": 0.25}
```

Use the existing async database fixture, or a narrow session double that retains the production update behavior. The test catches old merge semantics.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_kt_lpp_schema_adapter.py::test_diagnosis_profile_replaces_prior_unselected_knowledge_states -q`

Expected: FAIL because the current implementation merges prior graph entries.

- [ ] **Step 3: Write minimal implementation**

```python
profile.knowledge_graph = {
    str(state.get("skill_id") or state.get("skill_name")): self._mastery_probability(state)
    for state in output.get("knowledge_states", [])
    if isinstance(state, dict) and (state.get("skill_id") or state.get("skill_name"))
}
profile.weak_points = list(output.get("weak_points") or [])
```

If the current output has a structural graph, attach only this round's graph to this new mapping; never preserve a prior graph containing non-selected states.

- [ ] **Step 4: Run focused tests**

Run: `cd backend && pytest tests/test_kt_lpp_schema_adapter.py -q`

Expected: PASS.

### Task 3: Verify the resource-planning boundary

**Files:**
- Modify: `backend/tests/test_resource_recommender_compaction.py`

**Interfaces:**
- Consumes: a normalized diagnosis built from 334 predictions with 18 selected IDs.
- Produces: resource-recommender plan input containing only the source Top-18 projection.

- [ ] **Step 1: Write the regression test**

```python
def test_resource_recommender_plan_input_preserves_kt_top_18():
    diagnosis = normalized_334_prediction_fixture()
    plan_input = ResourceRecommenderAgent()._prepare_plan_input({"diagnosis_result": diagnosis})

    assert len(plan_input["diagnosis_result"]["knowledge_states"]) == 18
    assert len(plan_input["diagnosis_result"]["mastery_rates"]) == 18
```

- [ ] **Step 2: Run the regression suites**

Run: `cd backend && pytest tests/test_kt_lpp_schema_adapter.py tests/test_resource_recommender_compaction.py tests/test_decision_routing.py -q`

Expected: PASS.

## Plan Self-Review

- Task 1 applies the original skill's selected list at the earliest SmartTutor boundary.
- Task 2 prevents old full predictions from resurfacing via the profile.
- Task 3 protects the resource-recommender consumer contract.
- All identifiers are normalized to strings, matching the existing diagnosis contract.
