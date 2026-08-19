# Preserve KT Student ID Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Preserve a numeric student ID from the original user message in the shared context when the safety pipeline transforms the visible message.

**Architecture:** Add one private extractor in `safety_gate.py`. Before invoking the safety pipeline, copy a matched `学生/Student #?数字` value into `context["kt_student_id"]`; leave existing context values unchanged when no match exists. Existing `stage_executor` context flattening and `resolve_kt_student_id()` consume this field without further changes.

**Tech Stack:** Python 3.12, LangGraph `TutorState`, pytest, pytest-asyncio.

## Global Constraints

- Do not add permission checks in this change.
- Do not modify safety prompts, `TutorState`, stage scheduling, or KT runtime.
- Do not extract IDs from the transformed message.

---

### Task 1: Add regression coverage for transformed-message ID preservation

**Files:**
- Create: `backend/tests/test_safety_gate_student_id.py`
- Test: `backend/tests/test_safety_gate_student_id.py`

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_transform_preserves_student_id_in_shared_context(monkeypatch):
    monkeypatch.setattr(
        safety_gate_module,
        "_get_pipeline",
        lambda: FakePipeline(SafetyResult(
            action="TRANSFORM",
            original_query="可以对学生42做一次认知诊断吗？",
            transformed_query="学习认知诊断的隐私边界",
            safety_context={"risk_category": "D2"},
        )),
    )
    result = await safety_gate({
        "messages": [HumanMessage(content="可以对学生42做一次认知诊断吗？")],
        "context": {},
        "user_profile": {},
    })
    assert result["context"]["kt_student_id"] == "42"
    assert result["messages"][0].content == "学习认知诊断的隐私边界"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_safety_gate_student_id.py -q`

Expected: FAIL with `KeyError: 'kt_student_id'`, because the current safety gate only stores `context["safety"]`.

- [ ] **Step 3: Write minimal implementation**

Add a regex helper and call it before `SafetyPipeline.execute()`:

```python
_KT_STUDENT_ID_RE = re.compile(r"(?:学生|student)\s*#?\s*(\d+)", re.IGNORECASE)

def _extract_kt_student_id(message: str) -> str | None:
    match = _KT_STUDENT_ID_RE.search(message)
    return match.group(1) if match else None
```

Copy the matched value into the cloned `ctx` before the pipeline executes, preserving existing values when the current message has no match.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_safety_gate_student_id.py -q`

Expected: PASS.

- [ ] **Step 5: Run related tests**

Run: `cd backend && pytest tests/test_kt_lpp_schema_adapter.py -q`

Expected: PASS with no failures.

- [ ] **Step 6: Commit implementation**

```bash
git add backend/app/graph/nodes/safety_gate.py backend/tests/test_safety_gate_student_id.py
git commit -m "fix: preserve KT student ID across safety transform"
```

### Task 2: Sync the running Docker backend and verify the endpoint

**Files:**
- Modify in container: `/app/backend/app/graph/nodes/safety_gate.py`
- Test in container: `/app/backend/tests/test_safety_gate_student_id.py`

- [ ] **Step 1: Copy the two changed source files into the running container**

Use `docker cp` for only the two files, without rebuilding or changing model processes.

- [ ] **Step 2: Run the focused test inside the container**

Run: `docker exec smarttutor-v3 sh -lc 'cd /app/backend && pytest tests/test_safety_gate_student_id.py -q'`

Expected: PASS.

- [ ] **Step 3: Verify backend and frontend health**

Run inside the container:

```bash
curl -fsS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/health
curl -fsS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:80/
```

Expected: both return `200`.
