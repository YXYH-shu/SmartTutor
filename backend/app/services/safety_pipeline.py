"""Safety Pipeline – 5-stage safety assessment and transformation pipeline.

Stages:
  1. risk     – Detect whether the student query poses a safety risk.
  2. intent   – Identify the student's underlying intent.
  3. value    – Decide the action (TRANSFORM / SOFT_BLOCK / HARD_BLOCK / REFERRAL).
  4. education – Plan the educational direction for TRANSFORM cases.
  5. transform – Rewrite the original query into a safe, educational query.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from jinja2 import BaseLoader, Environment, StrictUndefined

from app.services.llm_client import LLMClient

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "prompts"

_STAGE_NAMES = [
    "safety_stage1_risk",
    "safety_stage2_intent",
    "safety_stage3_value",
    "safety_stage4_education",
    "safety_stage5_transform",
]

_jinja_env = Environment(loader=BaseLoader(), undefined=StrictUndefined)


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class SafetyResult:
    """Unified result returned by the safety pipeline."""

    action: str  # SAFE, TRANSFORM, SOFT_BLOCK, HARD_BLOCK, REFERRAL
    original_query: str
    transformed_query: str | None = None
    safety_context: dict | None = None
    blocked_response: str | None = None  # used for SOFT_BLOCK / HARD_BLOCK / REFERRAL


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class SafetyPipeline:
    """Orchestrates the 5-stage safety pipeline."""

    def __init__(self) -> None:
        self._llm = self._create_llm()
        self._prompts = self._load_prompts()

    # ------------------------------------------------------------------
    # Initialisation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _create_llm() -> LLMClient:
        """Create an LLMClient using the project-level settings."""
        return LLMClient()

    @staticmethod
    def _load_prompts() -> dict[str, dict[str, Any]]:
        """Load the 5 stage YAML configs into a dict keyed by stage name."""
        prompts: dict[str, dict[str, Any]] = {}
        for name in _STAGE_NAMES:
            path = _PROMPTS_DIR / f"{name}.yaml"
            if not path.exists():
                raise FileNotFoundError(f"Safety pipeline config not found: {path}")
            with open(path, "r", encoding="utf-8") as fh:
                prompts[name] = yaml.safe_load(fh)
        return prompts

    # ------------------------------------------------------------------
    # Core execution
    # ------------------------------------------------------------------

    async def execute(
        self,
        query: str,
        student_grade: str = "未知",
        conversation_context: str = "",
    ) -> SafetyResult:
        """Execute the full 5-stage safety pipeline."""

        # ---- Stage 1: Risk Detection ----
        risk_result = await self._run_stage("safety_stage1_risk", {
            "student_grade": student_grade,
            "user_query": query,
        })

        if not risk_result.get("risk_detected", False):
            return SafetyResult(action="SAFE", original_query=query)

        risk_category = risk_result.get("risk_category", "")
        risk_signal = risk_result.get("risk_signal", "")

        # ---- C-class: Direct Referral ----
        if risk_category == "C" or risk_result.get("referral", False):
            return SafetyResult(
                action="REFERRAL",
                original_query=query,
                blocked_response=(
                    "我注意到你的问题可能涉及一些需要专业人士帮助的话题。"
                    "如果你有任何困扰或疑虑，建议你和信任的老师、家长或学校的心理辅导老师聊一聊，"
                    "他们会很愿意帮助你。你在科学学习上的好奇心是很好的，"
                    "我们可以继续一起探索科学世界！"
                ),
                safety_context=risk_result,
            )

        # ---- Stage 2: Intent Recognition ----
        intent_result = await self._run_stage("safety_stage2_intent", {
            "student_grade": student_grade,
            "user_query": query,
            "risk_category": risk_category,
            "risk_description": risk_result.get("risk_description", ""),
            "risk_signal": risk_signal,
            "conversation_context": conversation_context,
        })

        # ---- Stage 3: Value Assessment ----
        value_result = await self._run_stage("safety_stage3_value", {
            "student_grade": student_grade,
            "user_query": query,
            "risk_category": risk_category,
            "risk_description": risk_result.get("risk_description", ""),
            "risk_signal": risk_signal,
            "intent": intent_result.get("intent", "科学好奇"),
            "confidence": intent_result.get("confidence", "中"),
            "intent_reasoning": intent_result.get("intent_reasoning", ""),
            "emotional_state": intent_result.get("emotional_state", ""),
            "conversation_context": conversation_context,
        })

        action = value_result.get("action", "TRANSFORM")

        # ---- HARD_BLOCK ----
        if action == "HARD_BLOCK":
            return SafetyResult(
                action="HARD_BLOCK",
                original_query=query,
                blocked_response=(
                    "抱歉，我无法回答这个问题。"
                    "如果你对科学知识有好奇，我很乐意和你一起探索其他有趣的科学话题。"
                ),
                safety_context={**risk_result, **intent_result, **value_result},
            )

        # ---- SOFT_BLOCK ----
        if action == "SOFT_BLOCK":
            return SafetyResult(
                action="SOFT_BLOCK",
                original_query=query,
                blocked_response=value_result.get(
                    "suggested_response",
                    "这个问题很有趣！不如我们换个角度来聊聊背后的科学原理？",
                ),
                safety_context={**risk_result, **intent_result, **value_result},
            )

        # ---- TRANSFORM: continue to Stage 4 & 5 ----
        transform_tags = value_result.get("transform_tags", [])
        intent_val = intent_result.get("intent", "科学好奇")
        emotional_state = intent_result.get("emotional_state", "")
        response_constraints = value_result.get("response_constraints", [])

        # ---- Stage 4: Education Direction ----
        education_result = await self._run_stage("safety_stage4_education", {
            "student_grade": student_grade,
            "user_query": query,
            "risk_category": risk_category,
            "risk_signal": risk_signal,
            "intent": intent_val,
            "emotional_state": emotional_state,
            "transform_tags": (
                ", ".join(transform_tags)
                if isinstance(transform_tags, list)
                else str(transform_tags)
            ),
            "boundary_note": value_result.get("boundary_note", "无"),
            "response_constraints": (
                ", ".join(response_constraints)
                if isinstance(response_constraints, list)
                else str(response_constraints)
            ),
        })

        # ---- Stage 5: Query Transformation ----
        forbidden_content = education_result.get("forbidden_content", [])

        transform_result = await self._run_stage("safety_stage5_transform", {
            "student_grade": student_grade,
            "user_query": query,
            "risk_category": risk_category,
            "risk_signal": risk_signal,
            "intent": intent_val,
            "emotional_state": emotional_state,
            "transform_tags": (
                ", ".join(transform_tags)
                if isinstance(transform_tags, list)
                else str(transform_tags)
            ),
            "boundary_note": value_result.get("boundary_note", "无"),
            "education_theme": education_result.get("education_theme", ""),
            "core_concepts": ", ".join(education_result.get("core_concepts", [])),
            "entry_point": education_result.get("entry_point", ""),
            "grade_adaptation": education_result.get("grade_adaptation", ""),
            "ethics_guidance": education_result.get("ethics_guidance", "无"),
            "behavior_guidance": education_result.get("behavior_guidance", "无"),
            "thinking_guidance": education_result.get("thinking_guidance", "无"),
            "emotion_response": education_result.get("emotion_response", "无"),
            "forbidden_content": (
                ", ".join(forbidden_content)
                if isinstance(forbidden_content, list)
                else str(forbidden_content)
            ),
            "response_constraints": (
                ", ".join(response_constraints)
                if isinstance(response_constraints, list)
                else str(response_constraints)
            ),
        })

        full_context = {
            **risk_result,
            "intent_result": intent_result,
            "value_result": value_result,
            "education_result": education_result,
            "transform_result": transform_result,
            "transform_tags": transform_tags,
            "risk_category": risk_category,
        }

        return SafetyResult(
            action="TRANSFORM",
            original_query=query,
            transformed_query=transform_result.get("transformed_query", query),
            safety_context=full_context,
        )

    # ------------------------------------------------------------------
    # Stage runner
    # ------------------------------------------------------------------

    async def _run_stage(
        self,
        stage_name: str,
        input_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Render the Jinja2 prompt, call the LLM, and parse the JSON response."""

        config = self._prompts[stage_name]
        template_text = config.get("prompt_template", "")
        llm_cfg = config.get("llm_config", {})

        # 1. Render the Jinja2 template with input data
        template = _jinja_env.from_string(template_text)
        rendered = template.render(**input_data)

        # 2. Call the LLM
        try:
            llm_result = await self._llm.chat_completion(
                prompt=rendered,
                system_prompt=None,
                model=llm_cfg.get("model"),
                temperature=llm_cfg.get("temperature", 0.3),
                max_tokens=llm_cfg.get("max_tokens"),
                response_format="json",
                thinking=llm_cfg.get("thinking", False),
            )
        except Exception as exc:
            logger.exception("LLM call failed for stage %s", stage_name)
            # If the LLM API itself refused due to content filter, treat as risk
            if _is_content_filter_error(exc):
                if stage_name == "safety_stage1_risk":
                    return {
                        "risk_detected": True,
                        "risk_category": "A",
                        "risk_description": "LLM API content filter triggered",
                        "risk_signal": "LLM API内容过滤器触发",
                        "referral": False,
                        "original_query": input_data.get("user_query", ""),
                    }
                # For later stages, the risk is already confirmed – return empty
                # so the pipeline proceeds with safe defaults
                return {}
            if stage_name == "safety_stage1_risk":
                return {"risk_detected": False, "risk_category": "无"}
            # Other stages: return a safe default
            return {}

        # 3. Parse the response
        raw_content = llm_result.get("content", {})
        if isinstance(raw_content, dict):
            return raw_content

        # Content is a string – parse it with tolerance for markdown fences
        return self._parse_json(raw_content)

    # ------------------------------------------------------------------
    # JSON parsing with fault tolerance
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        """Extract and parse JSON from LLM output, tolerating markdown fences."""
        if not text or not text.strip():
            return {}

        # Strip markdown code fences
        cleaned = re.sub(
            r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE
        )
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # Try to find the first { ... } block
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        logger.warning("Failed to parse JSON from LLM response: %s", text[:200])
        return {}


def _is_content_filter_error(exc: Exception) -> bool:
    """Detect non-retryable content filter / safety errors from LLM APIs."""
    exc_str = str(exc)
    if "'code': '1301'" in exc_str or '"code": "1301"' in exc_str:
        return True
    if "contentFilter" in exc_str:
        return True
    if "content_policy" in exc_str or "content management policy" in exc_str:
        return True
    return False
