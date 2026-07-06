from __future__ import annotations

from dataclasses import asdict
import os
import re
from typing import Any

from deepagents import create_deep_agent
from langchain_core.messages import AIMessage, HumanMessage

from chat_agent.llm import OpenAICompatibleChatModel
from chat_agent.models import OrchestrationResult, SkillDefinition
from chat_agent.session import ChatSession
from chat_agent.skill_markdown_executor import MissingSkillInputs


class ChatAgentTools:
    def __init__(self, orchestrator, skills: list[SkillDefinition]):
        self.orchestrator = orchestrator
        self.skills = skills
        self.sessions: dict[str, ChatSession] = {}

    def list_skills(self) -> list[dict[str, Any]]:
        """List skills registered in ChatAgent."""
        return [
            {
                "name": skill.name,
                "description": skill.description,
                "level": skill.level,
                "executor_name": skill.executor_name,
            }
            for skill in self.skills
        ]

    def run_workflow(self, message: str, session_id: str = "default") -> dict[str, Any]:
        """Run the ChatAgent workflow for a user message."""
        session = self._session(session_id)
        result = self.orchestrator.handle_message(message, session=session)
        payload = _orchestration_to_dict(result)
        payload["session_id"] = session.session_id
        payload["events"] = [event.__dict__ for event in session.events]
        return payload

    def run_skill(self, skill_name: str, inputs: dict[str, Any], session_id: str = "default") -> dict[str, Any]:
        """Run a registered skill through ChatAgent policy and the skill executor."""
        message = _message_from_inputs(skill_name, inputs)
        return self.run_workflow(message, session_id=session_id)

    def list_sessions(self) -> list[dict[str, Any]]:
        """List active in-memory ChatAgent sessions."""
        return [
            {
                "key": key,
                "session_id": session.session_id,
                "pending_skill": session.pending_skill,
                "pending_inputs": session.pending_inputs,
                "message_count": len(session.messages),
                "event_count": len(session.events),
            }
            for key, session in self.sessions.items()
        ]

    def _session(self, session_id: str) -> ChatSession:
        if session_id not in self.sessions:
            self.sessions[session_id] = ChatSession()
        return self.sessions[session_id]


def create_chat_deep_agent(
    orchestrator,
    skills: list[SkillDefinition],
    model: str | None = None,
    skill_sources: list[str] | None = None,
):
    tools = ChatAgentTools(orchestrator=orchestrator, skills=skills)
    return create_deep_agent(
        model=model,
        tools=[tools.list_skills, tools.list_sessions, tools.run_workflow, tools.run_skill],
        skills=skill_sources,
        system_prompt=_system_prompt(),
    )


class DeepAgentRuntime:
    def __init__(self, orchestrator, skills: list[SkillDefinition], config: dict[str, Any]):
        self.orchestrator = orchestrator
        self.skills = skills
        self.config = config

    def handle_message(self, message: str, session: ChatSession | None = None) -> OrchestrationResult:
        active_session = session or ChatSession()
        active_session.add_message("user", message)
        active_session.add_event("message_received", "收到用户消息。", user_message=message)

        if not self.is_configured():
            active_session.add_event("workflow_failed", "DeepAgent LLM 未配置。", error="llm_not_configured")
            raise RuntimeError("DeepAgent LLM is not configured.")

        active_session.add_event("deepagent_started", "DeepAgent 开始根据上下文判断是否调用 skill。")
        agent = self._build_agent(active_session)
        previous_result = active_session.last_result
        output = agent.invoke({"messages": _session_messages(active_session)})

        response = _last_ai_text(output.get("messages", []))
        tool_result = active_session.last_result if active_session.last_result is not previous_result else None
        if (
            tool_result
            and tool_result.skill_name == "kt-runtime-skill"
            and tool_result.final_response
            and not _requires_agent_rewrite(tool_result.final_response)
        ):
            response = tool_result.final_response
        response = _normalize_kt_skill_response(response, tool_result)

        result_status = tool_result.status if tool_result else "ok"
        result = OrchestrationResult(
            status=result_status,
            final_response=response,
            skill_name=tool_result.skill_name if tool_result else None,
            raw_result=tool_result.raw_result if tool_result else None,
            missing_inputs=tool_result.missing_inputs if tool_result else [],
        )
        active_session.add_message("assistant", response)
        active_session.last_result = result
        active_session.add_event("deepagent_finished", "DeepAgent 本轮处理完成。", status=result.status)
        active_session.add_event("workflow_finished", "对话工作流执行完成。", status=result.status)
        return result

    def is_configured(self) -> bool:
        return bool(_llm_base_url() and _llm_api_key() and _llm_model())

    def _build_agent(self, session: ChatSession):
        return create_deep_agent(
            model=_llm(),
            tools=[self._run_skill_tool(session)],
            system_prompt=self._system_prompt(),
            skills=None,
        )

    def _run_skill_tool(self, session: ChatSession):
        def run_skill(skill_name: str, inputs: dict[str, Any]) -> dict[str, Any]:
            """Run a registered local skill through its SKILL.md policy. Use skill_name from the registered skill catalog and provide inputs as a JSON object."""
            inputs = dict(inputs or {})
            if skill_name == "kt-runtime-skill":
                inputs = _with_session_history_context(inputs, session)
            session.update_slots(inputs)

            session.pending_skill = None
            session.pending_inputs = []
            session.add_event("skill_selected", f"DeepAgent 选择 skill：{skill_name}", skill_name=skill_name)
            session.add_event("skill_execution_started", "开始按 SKILL.md 执行 skill。", skill_name=skill_name, inputs=inputs)
            try:
                skill_result = self.orchestrator.registry.run_skill(skill_name, inputs, session=session)
            except MissingSkillInputs as exc:
                session.pending_skill = skill_name
                session.pending_inputs = exc.missing_inputs
                response = _missing_input_message(exc.missing_inputs)
                session.last_result = OrchestrationResult(
                    status="need_input",
                    final_response=response,
                    skill_name=skill_name,
                    raw_result=None,
                    missing_inputs=exc.missing_inputs,
                )
                session.add_event("slot_missing", "skill 参数不足，等待用户补充。", missing_inputs=exc.missing_inputs)
                return {
                    "status": "need_input",
                    "skill_name": skill_name,
                    "missing_inputs": exc.missing_inputs,
                    "message": response,
                }

            session.add_event("skill_execution_finished", "SKILL.md 执行完成。", skill_name=skill_name)
            session.add_event(
                "skill_result",
                "skill 返回结果。",
                skill_name=skill_name,
                status=str(skill_result.raw_json.get("status", "ok")),
                metrics=skill_result.metrics,
                raw_result=skill_result.raw_json,
                report_markdown=skill_result.report_markdown or "",
            )
            skill = self.orchestrator.registry.get_skill(skill_name)
            self.orchestrator.validator.validate(
                skill=skill,
                executor_name=skill_result.executor_name,
                command=None,
                output=skill_result.raw_json,
            )
            session.add_event("validation_passed", "skill 输出校验通过。", skill_name=skill_name)
            session.last_result = OrchestrationResult(
                status="ok",
                final_response=skill_result.report_markdown or "",
                skill_name=skill_name,
                raw_result=skill_result.raw_json,
            )
            return {
                "status": "ok",
                "skill_name": skill_name,
                "report_markdown": skill_result.report_markdown or "",
                "user_question_context": _user_question_context(inputs),
            }

        return run_skill

    def _system_prompt(self) -> str:
        return (
            "你是 ChatAgent，一个使用 DeepAgent 技术驱动本地 skills 的中文对话智能体。\n"
            "\n"
            "核心职责：\n"
            "- 和用户进行自然多轮对话。\n"
            "- 只能根据 skill description 判断是否调用 skill。\n"
            "- 当用户需要使用已注册 skill 时，必须调用 run_skill 工具，不要直接编造结果。\n"
            "- 根据已注册 skill 的 required_inputs 从多轮上下文中自动提取参数；缺哪个只追问哪个。\n"
            "- 如果 skill 返回的 report_markdown 包含 AGENT_REWRITE_REQUIRED，你必须根据 report_markdown 内的写作材料和参考模板生成替换内容；可以只输出该替换内容。\n"
            "- 生成 AGENT_REWRITE_REQUIRED 替换内容时，只改写该标记块内的自然语言分析和教学建议，不要改动主题判定、知识点集合表、掌握度表和诊断知识点明细；不要输出开场说明、分隔线或结尾说明。\n"
            "- run_skill 工具返回给你的内容是轻量结果；不要要求读取完整 raw_result 或 predictions。\n"
            "- 如果用户只是问你能做什么、怎么用、或普通闲聊，不要调用 KT 工具。\n"
            "- 不要编写临时 Python，不要绕开工具直接执行 skill。Level 1 skill 只能通过 run_skill 工具调用。\n"
            "\n"
            "已注册 skill：\n"
            + _skill_catalog(self.skills)
        )


def _orchestration_to_dict(result: OrchestrationResult) -> dict[str, Any]:
    return asdict(result)


def _message_from_inputs(skill_name: str, inputs: dict[str, Any]) -> str:
    if skill_name == "kt-runtime-skill":
        student_id = inputs.get("student_id", "")
        history_context = inputs.get("history_context", "")
        return f"帮学生 {student_id} 做 KT 学情分析。{history_context}"
    return str(inputs)


def _system_prompt() -> str:
    return (
        "You are ChatAgent, a local skill-aware agent. "
        "Always use ChatAgent tools for registered Level 1 skills. "
        "Read and obey SKILL.md policies; do not bypass the skill executor or execute ad hoc scripts."
    )


def _llm() -> OpenAICompatibleChatModel:
    return OpenAICompatibleChatModel(
        model=_llm_model(),
        base_url=_llm_base_url(),
        api_key=_llm_api_key(),
        timeout=float(os.getenv("CHATAGENT_LLM_TIMEOUT", "120")),
        temperature=float(os.getenv("CHATAGENT_LLM_TEMPERATURE", "0")),
    )


def _llm_base_url() -> str:
    return os.getenv("CHATAGENT_LLM_BASE_URL", "").strip().rstrip("/")


def _llm_api_key() -> str:
    return os.getenv("CHATAGENT_LLM_API_KEY", "").strip()


def _llm_model() -> str:
    return os.getenv("CHATAGENT_LLM_MODEL", "").strip()


def _session_messages(session: ChatSession) -> list[Any]:
    messages: list[Any] = []
    for message in session.messages:
        if message.role == "assistant":
            messages.append(AIMessage(content=message.content))
        else:
            messages.append(HumanMessage(content=message.content))
    return messages


def _last_ai_text(messages: list[Any]) -> str:
    for message in reversed(messages):
        if isinstance(message, AIMessage) and message.content:
            return str(message.content)
    return ""


def _requires_agent_rewrite(text: str) -> bool:
    return "AGENT_REWRITE_REQUIRED" in str(text or "")


def _normalize_kt_skill_response(response: str, tool_result: OrchestrationResult | None) -> str:
    if not tool_result or tool_result.skill_name != "kt-runtime-skill":
        return response
    report_markdown = tool_result.final_response or ""
    if not report_markdown or not _requires_agent_rewrite(report_markdown):
        return response
    if _is_complete_kt_report(response) and not _requires_agent_rewrite(response):
        return response
    assembled = _replace_agent_rewrite_block(report_markdown, response)
    return assembled or response


def _is_complete_kt_report(text: str) -> bool:
    report = str(text or "")
    required_sections = [
        "## 1. 主题判定",
        "## 2. 知识点集合",
        "## 3. 学情分析结果",
    ]
    has_required_sections = all(section in report for section in required_sections)
    has_detail_section = (
        "## 4. 诊断知识点明细" in report
        or "## 4. 选中知识点明细" in report
    )
    return has_required_sections and has_detail_section


def _replace_agent_rewrite_block(report_markdown: str, replacement: str) -> str:
    begin = "<!-- AGENT_REWRITE_REQUIRED_BEGIN -->"
    end = "<!-- AGENT_REWRITE_REQUIRED_END -->"
    begin_index = report_markdown.find(begin)
    end_index = report_markdown.find(end)
    if begin_index < 0 or end_index < 0 or end_index < begin_index:
        return ""

    before = report_markdown[:begin_index].rstrip()
    after = report_markdown[end_index + len(end) :].lstrip()
    replacement_text = _clean_agent_replacement(replacement)
    if not replacement_text:
        return ""
    return f"{before}\n\n{replacement_text}\n\n{after}".strip()


def _clean_agent_replacement(text: str) -> str:
    cleaned = str(text or "").strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    section_three_index = cleaned.find("## 3. 学情分析结果")
    if section_three_index >= 0:
        cleaned = cleaned[section_three_index:].strip()
    if cleaned.startswith("## 3. 学情分析结果"):
        marker = "自然语言分析"
        marker_index = cleaned.find(marker)
        if marker_index >= 0:
            cleaned = cleaned[marker_index + len(marker) :].strip()
    for section_title in ("\n## 4. 诊断知识点明细", "\n## 4. 选中知识点明细"):
        section_four_index = cleaned.find(section_title)
        if section_four_index >= 0:
            cleaned = cleaned[:section_four_index].strip()
            break
    cleaned = _strip_agent_wrapper_lines(cleaned)
    mastery_table_index = cleaned.find("\n| 知识点ID |")
    if mastery_table_index >= 0:
        cleaned = cleaned[:mastery_table_index].strip()
    return cleaned


def _strip_agent_wrapper_lines(text: str) -> str:
    lines = []
    for line in str(text or "").splitlines():
        stripped = line.strip()
        if stripped == "---":
            continue
        if re.search(r"^以下是.*学情分析报告", stripped):
            continue
        if re.search(r"^根据.*KT.*诊断结果.*以下是.*自然语言分析.*教学建议", stripped):
            continue
        if "以上自然语言分析" in stripped:
            continue
        if "报告其余部分" in stripped and "保持不变" in stripped:
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _skill_catalog(skills: list[SkillDefinition]) -> str:
    lines: list[str] = []
    for skill in skills:
        lines.append(f"- name: {skill.name}")
        lines.append(f"  description: {skill.description}")
        lines.append(f"  executor: {skill.executor_name or 'none'}")
        lines.append(f"  level: {skill.level}")
        if skill.policy.required_inputs:
            lines.append(f"  required_inputs: {', '.join(skill.policy.required_inputs)}")
        if skill.policy.default_entrypoints:
            lines.append(f"  default_entrypoints: {', '.join(skill.policy.default_entrypoints)}")
        if skill.policy.forbidden_actions:
            lines.append(f"  forbidden_actions: {', '.join(skill.policy.forbidden_actions)}")
    return "\n".join(lines)


def _with_session_history_context(inputs: dict[str, Any], session: ChatSession) -> dict[str, Any]:
    explicit_context = str(inputs.get("history_context", "")).strip()
    history_context = _recent_learning_context(session)
    if not history_context and not explicit_context:
        return inputs
    enriched = dict(inputs)
    if explicit_context and history_context and explicit_context not in history_context:
        enriched["history_context"] = f"{history_context}\n{explicit_context}"
    else:
        enriched["history_context"] = explicit_context or history_context
    return enriched


def _user_question_context(inputs: dict[str, Any]) -> str:
    parts: list[str] = []
    history_context = str(inputs.get("history_context", "")).strip()
    if history_context:
        parts.append(history_context)
    historical_questions = inputs.get("historical_questions")
    if isinstance(historical_questions, list):
        parts.extend(str(item).strip() for item in historical_questions if str(item).strip())
    elif historical_questions:
        parts.append(str(historical_questions).strip())
    return "\n".join(part for part in parts if part).strip()


def _recent_learning_context(session: ChatSession, max_messages: int = 4, max_chars: int = 1200) -> str:
    parts: list[str] = []
    for message in reversed(session.messages):
        if message.role != "user":
            continue
        text = message.content.strip()
        if not text:
            continue
        if _is_analysis_request(text) or _is_identity_only(text):
            continue
        if _is_learning_context_message(text):
            parts.append(text)
        if len(parts) >= max_messages:
            break
    parts.reverse()
    context = "\n".join(parts).strip()
    if len(context) <= max_chars:
        return context
    return context[-max_chars:]


def _is_analysis_request(text: str) -> bool:
    markers = [
        "学情分析",
        "学习情况",
        "掌握情况",
        "知识点掌握",
        "诊断",
        "预测掌握",
        "分析一下我的学情",
    ]
    return any(marker in text for marker in markers)


def _is_identity_only(text: str) -> bool:
    compact = "".join(ch for ch in text if ch.isalnum())
    if len(compact) > 24:
        return False
    has_student_id = "学生" in text and ("ID" in text.upper() or "id" in text)
    learning_terms = ["学习", "学科学", "学数学", "为什么", "怎么", "吗", "？", "?"]
    return has_student_id and not any(term in text for term in learning_terms)


def _is_learning_context_message(text: str) -> bool:
    learning_terms = [
        "学",
        "学习",
        "最近",
        "题",
        "概念",
        "知识点",
        "为什么",
        "什么",
        "怎么",
        "如何",
        "数学",
        "物理",
        "科学",
        "化学",
        "生物",
        "课程",
        "课堂",
        "刚刚",
        "聊",
        "讲",
        "问",
        "关于",
    ]
    return any(term in text for term in learning_terms) or "?" in text or "？" in text


def _missing_input_message(missing_inputs: list[str]) -> str:
    if missing_inputs == ["student_id"]:
        return "请补充学生 ID。"
    return "请补充缺少的 skill 输入：" + "、".join(missing_inputs) + "。"
