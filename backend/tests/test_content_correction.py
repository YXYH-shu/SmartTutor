from __future__ import annotations

import importlib

import pytest
from langchain_core.messages import HumanMessage

correction_module = importlib.import_module("app.graph.nodes.content_correction")
regeneration_module = importlib.import_module("app.graph.nodes.content_regeneration")
builder_module = importlib.import_module("app.graph.builder")


def _state(response: str, *, regeneration_count: int = 0) -> dict:
    return {
        "user_id": "user-1",
        "conversation_id": "conversation-1",
        "messages": [HumanMessage(content="电流为什么会影响肌肉？")],
        "current_stage": "teaching",
        "final_response": response,
        "user_profile": {"current_level": "初中"},
        "context": {
            "turn_id": "turn-1",
            "_content_regeneration_count": regeneration_count,
            "emotion_analyzer": {"emotion": "好奇", "intensity": 0.6},
        },
    }


def _audit(
    action: str,
    *,
    patched_response: str = "",
    passed: bool = True,
    issues: list[str] | None = None,
) -> dict:
    return {
        "action": action,
        "issues": issues or [],
        "patched_response": patched_response,
        "checks": {
            "scientific_reliability": passed,
            "educational_completeness": passed,
            "structural_clarity": passed,
            "content_safety": passed,
        },
    }


class StubAgent:
    def __init__(self, output: dict):
        self.output = output
        self.calls: list[dict] = []

    async def execute(self, *, input_data, context):
        self.calls.append(input_data)
        return {"output": self.output}


@pytest.mark.asyncio
async def test_pass_preserves_original_exactly_and_has_no_emotion_input(monkeypatch):
    original = "## 原理\n\n1. 电流刺激神经。\n2. 神经控制肌肉。  "
    # PASS must ignore any text smuggled into patched_response.
    agent = StubAgent(_audit("PASS", patched_response="偷偷重写"))
    monkeypatch.setattr(correction_module, "get_agent", lambda name: agent)

    result = await correction_module.content_correction(_state(original))

    assert result["final_response"] == original
    assert result["context"]["content_corrector"]["action"] == "PASS"
    assert result["context"]["content_corrector"]["status"] == "passed"
    assert "emotion_state" not in agent.calls[0]
    assert "emotion_analyzer" not in agent.calls[0]


@pytest.mark.asyncio
async def test_content_correction_compacts_safety_trace_before_llm(monkeypatch):
    agent = StubAgent(_audit("PASS"))
    monkeypatch.setattr(correction_module, "get_agent", lambda name: agent)
    state = _state("## 回答\n\n1. 原理。\n2. 边界。")
    state["context"]["safety_context"] = {
        "branch": "GUIDE",
        "risk_category": "A",
        "core_topic": "危险反应",
        "forbidden_content": ["危险操作步骤"],
        "classifier": {"large_trace": "不应进入内容矫正提示词"},
        "guidance_skill": {
            "education_domain": "science_safety",
            "safe_query": "为什么危险反应需要专业控制？",
            "subject_options": [{"large_tree": "不应进入内容矫正提示词"}],
        },
    }

    await correction_module.content_correction(state)

    constraints = agent.calls[0]["safety_constraints"]
    assert constraints["branch"] == "GUIDE"
    assert constraints["core_topic"] == "危险反应"
    assert constraints["guidance"]["education_domain"] == "science_safety"
    assert "classifier" not in constraints
    assert "guidance_skill" not in constraints
    assert "subject_options" not in constraints["guidance"]


@pytest.mark.asyncio
async def test_valid_local_patch_is_accepted(monkeypatch):
    original = "## 步骤\n\n1. 断开电源。\n2. 检查设备。"
    patched = "## 步骤\n\n1. 先断开电源，避免带电检查。\n2. 检查设备。"
    agent = StubAgent(_audit("PATCH", patched_response=patched))
    monkeypatch.setattr(correction_module, "get_agent", lambda name: agent)

    result = await correction_module.content_correction(_state(original))

    assert result["final_response"] == patched
    assert result["context"]["content_corrector"]["action"] == "PATCH"
    assert result["context"]["content_corrector"]["status"] == "patched"


@pytest.mark.asyncio
async def test_full_rewrite_disguised_as_patch_is_rejected(monkeypatch):
    original = "## 步骤\n\n1. 第一步。\n2. 第二步。\n3. 第三步。"
    flattened = "把事情做完即可。"
    agent = StubAgent(_audit("PATCH", patched_response=flattened))
    monkeypatch.setattr(correction_module, "get_agent", lambda name: agent)

    result = await correction_module.content_correction(_state(original))
    audit = result["context"]["content_corrector"]

    assert result["final_response"] == original
    assert audit["action"] == "REGENERATE"
    assert audit["status"] == "patch_rejected"
    assert builder_module._route_after_correction(result) == "regenerate_content"


@pytest.mark.asyncio
async def test_regenerate_is_limited_to_one_upstream_rewrite(monkeypatch):
    agent = StubAgent(_audit("REGENERATE", issues=["回答过短", "缺少结构"]))
    monkeypatch.setattr(correction_module, "get_agent", lambda name: agent)

    first = await correction_module.content_correction(_state("太短"))
    assert first["context"]["content_corrector"]["action"] == "REGENERATE"

    second = await correction_module.content_correction(
        _state("重新生成后的回答", regeneration_count=1)
    )
    assert second["final_response"] == "重新生成后的回答"
    assert second["context"]["content_corrector"]["action"] == "PASS"
    assert second["context"]["content_corrector"]["status"] == "regeneration_limit"


@pytest.mark.asyncio
async def test_regeneration_returns_issues_to_knowledge_responder(monkeypatch):
    responder = StubAgent({
        "response_text": "## 完整回答\n\n1. 结论。\n2. 原理。\n3. 注意事项。",
        "topic_tags": ["电流"],
        "confidence": 0.9,
    })
    monkeypatch.setattr(regeneration_module, "get_agent", lambda name: responder)
    state = _state("太短")
    state["context"]["content_corrector"] = {
        "action": "REGENERATE",
        "issues": ["回答过短", "缺少结构"],
    }

    result = await regeneration_module.content_regeneration(state)

    assert result["final_response"].startswith("## 完整回答")
    assert result["context"]["_content_regeneration_count"] == 1
    assert responder.calls[0]["regeneration_required"] is True
    assert responder.calls[0]["correction_issues"] == ["回答过短", "缺少结构"]
    assert responder.calls[0]["previous_response"] == "太短"


@pytest.mark.asyncio
async def test_audit_error_passes_original(monkeypatch):
    class BrokenAgent:
        async def execute(self, *, input_data, context):
            raise RuntimeError("LLM unavailable")

    monkeypatch.setattr(correction_module, "get_agent", lambda name: BrokenAgent())
    result = await correction_module.content_correction(_state("可靠原回答"))

    assert result["final_response"] == "可靠原回答"
    assert result["context"]["content_corrector"]["action"] == "PASS"
    assert result["context"]["content_corrector"]["status"] == "audit_fallback"


def test_normal_routes_end_at_correction_gate():
    assert builder_module._route_after_decide({"decision": "finish"}) == "correct_content"
    assert builder_module._route_after_agent({"next_agents": []}) == "correct_content"


@pytest.mark.parametrize("branch", ["REJECT", "GUIDE"])
def test_direct_safety_responses_bypass_correction_gate(branch: str):
    assert builder_module._route_after_safety({"safety_branch": branch}) == "assemble_response"


# ---------------------------------------------------------------------------
# V2.5 display fields: must be additive and must never change gate decisions
# ---------------------------------------------------------------------------
_V25_KEYS = {"scores", "severity", "issue_details", "patches", "summary", "change_ratio"}


@pytest.mark.asyncio
async def test_v25_fields_default_safely_when_model_omits_them(monkeypatch):
    # A V2.0-style model output (no V2.5 fields) must still work unchanged.
    agent = StubAgent(_audit("PASS"))
    monkeypatch.setattr(correction_module, "get_agent", lambda name: agent)

    result = await correction_module.content_correction(_state("## 回答\n\n1. 原理。"))
    audit = result["context"]["content_corrector"]

    assert _V25_KEYS <= set(audit)
    assert audit["action"] == "PASS" and audit["status"] == "passed"
    assert all(v is None for v in audit["scores"].values())
    assert audit["severity"] is None
    assert audit["issue_details"] == [] and audit["patches"] == []
    assert audit["change_ratio"] == 0.0


@pytest.mark.asyncio
async def test_v25_patch_fields_are_normalized(monkeypatch):
    filler = "\n".join(
        f"{n}. 电流通过生物组织时会产生热效应，并可能干扰神经、肌肉和心脏的正常电活动，需要做好绝缘与隔离。"
        for n in range(2, 12)
    )
    original = f"## 原理\n\n1. 体型越大的动物，受到电击时越安全。\n{filler}"
    patched = f"## 原理\n\n1. 即使是大象这样庞大的动物，也需要防范电击带来的伤害。\n{filler}"
    output = _audit("PATCH", patched_response=patched)
    output.update(
        {
            "scores": {
                "scientific_argumentation": 86,
                "metacognitive_guidance": 94.4,
                "scientific_discourse": 120,
                "content_safety": "高",
            },
            "severity": "minor",
            "issue_details": [
                {"dimension": "scientific_argumentation", "problem": "体型决定安全性", "reason": "缺少条件限定"},
                "bad-item",
                {"problem": ""},
            ],
            "patches": [
                {"before": "体型越大的动物，受到电击时越安全。", "after": "即使是大象这样庞大的动物，也需要防范电击带来的伤害。", "reason": "去掉绝对化判断"},
                {"before": "原文里根本没有这句", "after": "x", "reason": "应被丢弃"},
            ],
            "summary": "仅修正一处科学性表述",
        }
    )
    agent = StubAgent(output)
    monkeypatch.setattr(correction_module, "get_agent", lambda name: agent)

    result = await correction_module.content_correction(_state(original))
    audit = result["context"]["content_corrector"]

    assert result["final_response"] == patched
    assert audit["status"] == "patched"
    assert audit["scores"] == {
        "scientific_argumentation": 86,
        "metacognitive_guidance": 94,
        "scientific_discourse": 100,
        "content_safety": None,
    }
    assert audit["severity"] == "minor"
    assert len(audit["issue_details"]) == 1
    assert [p["reason"] for p in audit["patches"]] == ["去掉绝对化判断"]
    assert 0 < audit["change_ratio"] < 0.2


@pytest.mark.asyncio
async def test_v25_patches_derived_from_diff_when_model_gives_none(monkeypatch):
    original = "## 步骤\n\n1. 断开电源。\n2. 检查设备。"
    patched = "## 步骤\n\n1. 先断开电源，避免带电检查。\n2. 检查设备。"
    agent = StubAgent(_audit("PATCH", patched_response=patched))
    monkeypatch.setattr(correction_module, "get_agent", lambda name: agent)

    audit = (await correction_module.content_correction(_state(original)))["context"]["content_corrector"]

    assert audit["patches"] == [
        {"before": "1. 断开电源。", "after": "1. 先断开电源，避免带电检查。", "reason": ""}
    ]


@pytest.mark.asyncio
async def test_v25_garbage_fields_never_break_the_gate(monkeypatch):
    output = _audit("PASS")
    output.update(
        {"scores": "oops", "severity": 7, "issue_details": {"a": 1}, "patches": "x", "summary": 5}
    )
    agent = StubAgent(output)
    monkeypatch.setattr(correction_module, "get_agent", lambda name: agent)

    result = await correction_module.content_correction(_state("可靠回答"))
    audit = result["context"]["content_corrector"]

    assert result["final_response"] == "可靠回答"
    assert audit["action"] == "PASS" and audit["status"] == "passed"
    assert audit["severity"] is None and audit["summary"] == ""


@pytest.mark.asyncio
async def test_v25_fields_do_not_leak_into_regeneration_input(monkeypatch):
    # Regeneration must keep reading only action/issues, never the new fields.
    responder = StubAgent({"response_text": "## 重写\n\n1. 内容。", "topic_tags": [], "confidence": 0.9})
    monkeypatch.setattr(regeneration_module, "get_agent", lambda name: responder)
    state = _state("太短")
    state["context"]["content_corrector"] = {
        "action": "REGENERATE",
        "issues": ["回答过短"],
        "scores": {"scientific_argumentation": 10},
        "patches": [],
    }

    await regeneration_module.content_regeneration(state)

    assert responder.calls[0]["correction_issues"] == ["回答过短"]


@pytest.mark.asyncio
async def test_v25_dimension_notes_and_evidence_are_validated(monkeypatch):
    original = "## 原理\n\n1. **电流的热效应**：电流通过导体时会产生热量。\n2. 要做好绝缘与隔离。"
    output = _audit("PASS")
    output.update(
        {
            "dimension_notes": {
                "scientific_argumentation": "热效应的因果关系表述准确",
                "metacognitive_guidance": 5,
            },
            "dimension_evidence": {
                "scientific_argumentation": "电流通过导体时会产生热量。",
                "metacognitive_guidance": "原文里根本没有这句话",
                "scientific_discourse": "要做好绝缘与隔离",
                "content_safety": "x" * 200,
            },
        }
    )
    agent = StubAgent(output)
    monkeypatch.setattr(correction_module, "get_agent", lambda name: agent)

    audit = (await correction_module.content_correction(_state(original)))["context"]["content_corrector"]

    assert audit["action"] == "PASS" and audit["status"] == "passed"
    assert audit["dimension_notes"]["scientific_argumentation"] == "热效应的因果关系表述准确"
    assert audit["dimension_notes"]["metacognitive_guidance"] == ""
    ev = audit["dimension_evidence"]
    assert ev["scientific_argumentation"] == "电流通过导体时会产生热量。"
    assert ev["scientific_discourse"] == "要做好绝缘与隔离"  # markdown/空白差异不影响匹配
    assert ev["metacognitive_guidance"] == ""  # 编造的引用被丢弃
    assert ev["content_safety"] == ""  # 过长的引用被丢弃


@pytest.mark.asyncio
async def test_v25_notes_default_when_missing(monkeypatch):
    agent = StubAgent(_audit("PASS"))
    monkeypatch.setattr(correction_module, "get_agent", lambda name: agent)
    audit = (await correction_module.content_correction(_state("可靠回答")))["context"]["content_corrector"]
    assert set(audit["dimension_notes"]) == set(audit["dimension_evidence"]) == {
        "scientific_argumentation", "metacognitive_guidance", "scientific_discourse", "content_safety"
    }
    assert all(v == "" for v in audit["dimension_notes"].values())
