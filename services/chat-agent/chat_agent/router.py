from __future__ import annotations

import re

from chat_agent.models import RouterDecision


STUDENT_ID_RE = re.compile(r"(?:学生(?:\s*ID)?|student(?:_id)?\s*)\s*(?:是|为|=|:|：)?\s*(VSTU\d+|\d+)", re.IGNORECASE)
BARE_STUDENT_ID_RE = re.compile(r"^\s*(VSTU\d+|\d+)\s*$", re.IGNORECASE)


class RuleBasedRouter:
    def route(self, message: str) -> RouterDecision:
        if not self._looks_like_kt(message):
            return RouterDecision(skill_name=None, reason="No matching skill")

        inputs = self.extract_kt_inputs(message)
        missing = self.missing_kt_inputs(inputs)

        return RouterDecision(
            skill_name="kt-runtime-skill",
            inputs=inputs,
            missing_inputs=missing,
            reason="KT learning analysis request",
        )

    def is_cancel(self, message: str) -> bool:
        return message.strip() in {"取消", "不用了", "先不做了", "退出", "停止"}

    def _looks_like_kt(self, message: str) -> bool:
        normalized = message.strip()
        if not normalized:
            return False

        has_student_id = self._extract_student_id(normalized) is not None
        if not has_student_id and any(
            phrase in normalized
            for phrase in ["你能", "你可以", "能不能", "能做什么", "介绍一下", "是什么", "怎么用", "如何使用"]
        ):
            return False

        has_domain = any(token in normalized for token in ["KT", "kt", "学情", "掌握", "知识点", "预测", "知识追踪"])
        has_action = any(token in normalized for token in ["做", "运行", "分析", "预测", "评估", "生成", "看一下", "测一下"])
        return has_domain and (has_action or has_student_id)

    def extract_kt_inputs(
        self,
        message: str,
        allow_message_as_context: bool = False,
        allow_bare_student_id: bool = False,
        expected_inputs: list[str] | None = None,
    ) -> dict[str, str]:
        inputs: dict[str, str] = {}
        expected = set(expected_inputs or ["student_id", "history_context"])

        if "student_id" in expected:
            student_id = self._extract_student_id(message, allow_bare_student_id=allow_bare_student_id)
            if student_id:
                inputs["student_id"] = student_id

        if "history_context" in expected:
            history_context = self._extract_history_context(message)
            if history_context:
                inputs["history_context"] = history_context
            elif allow_message_as_context and self._looks_like_history_context(message):
                inputs["history_context"] = message.strip()

        return inputs

    def missing_kt_inputs(self, inputs: dict[str, str], required_inputs: list[str] | None = None) -> list[str]:
        required = required_inputs or ["student_id"]
        missing: list[str] = []
        if "student_id" in required and not inputs.get("student_id"):
            missing.append("student_id")
        if "history_context" in required and not inputs.get("history_context"):
            missing.append("history_context")
        return missing

    def _extract_student_id(self, message: str, allow_bare_student_id: bool = False) -> str | None:
        match = STUDENT_ID_RE.search(message)
        if match:
            return match.group(1)
        if allow_bare_student_id:
            bare_match = BARE_STUDENT_ID_RE.search(message)
            if bare_match:
                return bare_match.group(1)
        return None

    def _extract_history_context(self, message: str) -> str | None:
        markers = ["学生最近", "学习上下文", "history_context", "上下文"]
        for marker in markers:
            index = message.find(marker)
            if index >= 0:
                return message[index:].strip(" \n")
        return None

    def _looks_like_history_context(self, message: str) -> bool:
        normalized = message.strip()
        return any(
            token in normalized
            for token in ["最近", "在学", "学习", "答题", "错题", "掌握", "薄弱", "知识点", "章节", "课程"]
        )
