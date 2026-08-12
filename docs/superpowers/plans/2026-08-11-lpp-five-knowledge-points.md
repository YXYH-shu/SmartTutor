# LPP Five Knowledge Points Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Return an ordered, stable P1--P5 knowledge-point path without changing the current DSMOEA/REKT question-level search.

**Architecture:** The runtime derives five distinct knowledge points from its existing ACE-ranked candidates and question-level fallback data. The SmartTutor adapter validates and projects that list, then overwrites the agent's path fields with five knowledge-point stages. Question payloads remain internal runtime compatibility data only.

**Tech Stack:** Python 3, pytest, existing LPP Runtime and FastAPI agent adapter.

## Global Constraints

- Preserve the existing planning rationale, learning-objective, and adaptive-rule templates.
- Do not modify DSMOEA/REKT search or scoring.
- Expose exactly five distinct ordered knowledge points, or an explicit unavailable result.
- Do not expose recommendation questions in the final learning-plan response or LLM prompt.

---

### Task 1: Runtime knowledge-point recommendation

**Files:**
- Modify: `services/lpp-skill/scripts/run_lpp.py`
- Test: `services/lpp-skill/tests/test_run_lpp.py` or existing runtime test location

**Interfaces:**
- Produces `recommendation.knowledge_points: list[dict]`, each with `order`, `knowledge_point_id`, and `knowledge_point_name`.

- [ ] Write a failing runtime test for five distinct ACE-priority knowledge points.
- [ ] Run the test and verify it fails because the runtime emits only questions.
- [ ] Add the smallest deterministic knowledge-point builder and publish it beside the internal question list.
- [ ] Run the runtime test and verify it passes.

### Task 2: Adapter and response contract

**Files:**
- Modify: `backend/app/services/lpp_integration.py`
- Modify: `backend/app/services/agents/learning_path.py`
- Modify: `backend/app/services/response_context.py`
- Modify: `backend/config/prompts/learning_path.yaml`
- Test: `backend/tests/test_kt_lpp_schema_adapter.py`

**Interfaces:**
- Consumes the runtime's ordered five-point list.
- Produces `recommended_knowledge_points`, `main_path_sequence`, and five P1--P5 knowledge-point stages.

- [ ] Write failing adapter tests for validation, prompt compaction, and final public output.
- [ ] Run the targeted tests and verify they fail against question-first output.
- [ ] Implement the smallest validation/projection/finalization changes.
- [ ] Run the targeted tests and verify they pass.

### Task 3: Deploy and verify live container

**Files:**
- Mirror modified runtime and backend files to `/app/backend` / `/app/services/lpp-skill` in `smarttutor-v3`.

- [ ] Run static and targeted pytest verification in the container.
- [ ] Restart only `smarttutor-v3`.
- [ ] Verify HTTP health endpoints and inspect logs for startup errors.
