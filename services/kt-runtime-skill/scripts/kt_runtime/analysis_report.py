from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from kt_runtime.config import load_runtime_config
from kt_runtime.contracts import KTPredictRequest, KTPredictResponse, Prediction
from kt_runtime.student_source import load_kp_catalog_from_config
from kt_runtime.ngram_selector import select_relevant_knowledge_points


_SKILL_ROOT = Path(__file__).resolve().parents[2]
_LEARNING_ANALYSIS_TEMPLATE_PATH = (
    _SKILL_ROOT / "assets" / "report-templates" / "learning-analysis-style-template.md"
)


def attach_analysis_report(
    payload: dict[str, Any],
    request: KTPredictRequest,
    response: KTPredictResponse,
) -> KTPredictResponse:
    report_settings = _report_settings(payload, {})
    if report_settings.get("enabled", True) is False:
        return response

    response.llm_analysis = build_analysis_report(payload, request, response)
    return response


def build_analysis_report(
    payload: dict[str, Any],
    request: KTPredictRequest,
    response: KTPredictResponse,
) -> dict[str, Any]:
    context = _analysis_context(payload)
    config = load_runtime_config(context["runtime_config_path"] or None)
    report_settings = _report_settings(payload, config)
    catalog = load_kp_catalog_from_config(config)
    recent_window = int(context["sequence_summary"].get("recent_window", 20))

    candidate_rows = _candidate_rows(request, response.predictions, catalog, recent_window)
    selected = select_relevant_knowledge_points(
        candidate_rows,
        initial_query=context["initial_query"],
        history_context=context["history_context"],
        recent_interactions=context["recent_interactions"],
        top_k=min(int(report_settings.get("max_knowledge_points", 18)), len(candidate_rows) or 1),
    )
    if not selected:
        selected = candidate_rows[: int(report_settings.get("max_knowledge_points", 18))]

    risk_flags = _detect_risk_flags(context["initial_query"], context["history_context"])
    knowledge_points = _build_knowledge_points(selected, context)
    mastery_rows = _build_mastery_rows(selected, risk_flags)
    learning_analysis = _build_learning_analysis(selected, mastery_rows, risk_flags, context)
    theme_judgement = _build_theme_judgement(selected, context, risk_flags)
    analysis_process = _build_analysis_process(context, selected, response.model_info)
    selected_knowledge_points = _selected_knowledge_points(selected)
    report_markdown = _render_report_markdown(
        theme_judgement=theme_judgement,
        knowledge_points=knowledge_points,
        learning_analysis=learning_analysis,
        mastery_rows=mastery_rows,
        analysis_process=analysis_process,
        selected_knowledge_points=selected_knowledge_points,
    )

    return {
        "report_version": "science_learning_diagnosis.v2",
        "selection_method": {
            "name": "context_relevance",
            "description": "基于学习上下文与知识点描述的相关性排序。",
            "selected_count": len(selected),
        },
        "theme_judgement": theme_judgement,
        "knowledge_points": knowledge_points,
        "analysis_process": analysis_process,
        "learning_analysis": learning_analysis,
        "agent_revision_task": learning_analysis,
        "mastery_table": mastery_rows,
        "selected_knowledge_points": selected_knowledge_points,
        "report_markdown": report_markdown,
    }


def _report_settings(payload: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    analysis_cfg = config.get("analysis", {}) if isinstance(config, dict) else {}
    return {
        "enabled": bool(payload.get("analysis_enabled", analysis_cfg.get("enabled", True))),
        "max_knowledge_points": int(analysis_cfg.get("max_knowledge_points", 18)),
    }


def _analysis_context(payload: dict[str, Any]) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    nested = payload.get("analysis_context", {})
    nested = nested if isinstance(nested, dict) else {}

    summary = nested.get("sequence_summary")
    summary = summary if isinstance(summary, dict) else {}
    return {
        "initial_query": str(nested.get("initial_query") or payload.get("initial_query") or ""),
        "history_context": str(nested.get("history_context") or payload.get("history_context") or ""),
        "trace_source": str(nested.get("trace_source") or "direct_request"),
        "runtime_config_path": str(nested.get("runtime_config_path") or payload.get("runtime_config_path") or ""),
        "student_profile": nested.get("student_profile") if isinstance(nested.get("student_profile"), dict) else {},
        "sequence_summary": summary,
        "recent_interactions": nested.get("recent_interactions") if isinstance(nested.get("recent_interactions"), list) else [],
    }


def _candidate_rows(
    request: KTPredictRequest,
    predictions: list[Prediction],
    catalog: dict[int, dict[str, Any]],
    recent_window: int,
) -> list[dict[str, Any]]:
    history_counter = Counter(obs.skill_id for obs in request.student_trace)
    correct_counter = Counter()
    recent_counter = Counter(obs.skill_id for obs in request.student_trace[-recent_window:])
    recent_correct_counter = Counter()

    for obs in request.student_trace:
        correct_counter[obs.skill_id] += int(obs.correct)
    for obs in request.student_trace[-recent_window:]:
        recent_correct_counter[obs.skill_id] += int(obs.correct)

    rows = []
    for prediction in predictions:
        skill_id = int(prediction.target["skill_id"])
        meta = catalog.get(skill_id, {})
        history_count = int(history_counter.get(skill_id, 0))
        recent_count = int(recent_counter.get(skill_id, 0))
        rows.append(
            {
                "skill_id": skill_id,
                "report_skill_id": f"KP{skill_id:03d}",
                "knowledge_point_name": str(meta.get("knowledge_point_name") or f"知识点 {skill_id}"),
                "knowledge_point_description": str(meta.get("knowledge_point_description") or ""),
                "topic_id": meta.get("topic_id"),
                "topic_name": str(meta.get("topic_name") or ""),
                "domain_id": meta.get("domain_id"),
                "domain_name": str(meta.get("domain_name") or ""),
                "skill_names": list(meta.get("skill_names") or []),
                "type": _classify_point_type(meta),
                "probability_correct": float(prediction.probability_correct or 0.0),
                "mastery_status": str(prediction.extras.get("mastery_status") or ""),
                "mastery_percent": prediction.extras.get("mastery_percent"),
                "history_count": history_count,
                "history_accuracy": (
                    correct_counter[skill_id] / history_count if history_count else None
                ),
                "recent_count": recent_count,
                "recent_accuracy": (
                    recent_correct_counter[skill_id] / recent_count if recent_count else None
                ),
                "prediction": prediction,
            }
        )
    return rows


def _classify_point_type(meta: dict[str, Any]) -> str:
    text = " ".join(
        [
            str(meta.get("knowledge_point_name") or ""),
            str(meta.get("knowledge_point_description") or ""),
            " ".join(str(item) for item in meta.get("skill_names", [])),
        ]
    )
    if any(token in text for token in ["安全", "责任", "保护", "规范", "伦理"]):
        return "价值"
    if any(token in text for token in ["实验", "测量", "设计", "比较", "分析", "表达", "图示"]):
        return "方法"
    if any(token in text for token in ["规律", "变化", "关系", "原理", "影响", "作用"]):
        return "规律"
    return "概念"


def _build_knowledge_points(
    selected: list[dict[str, Any]],
    context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    rows = []
    for item in selected:
        rows.append(
            {
                "knowledge_point_id": item["report_skill_id"],
                "source_skill_id": int(item["skill_id"]),
                "knowledge_point_name": item["knowledge_point_name"],
                "type": item["type"],
                "selection_bucket": item.get("selection_bucket", ""),
            }
        )
    return rows


def _build_mastery_rows(selected: list[dict[str, Any]], risk_flags: list[str]) -> list[dict[str, Any]]:
    rows = []
    for item in selected:
        raw_mastery = item.get("mastery_percent")
        if raw_mastery is None:
            raw_mastery = float(item["probability_correct"]) * 100
        mastery_status = str(item.get("mastery_status") or "-")

        rows.append(
            {
                "skill_id": item["report_skill_id"],
                "source_skill_id": int(item["skill_id"]),
                "knowledge_point_name": item["knowledge_point_name"],
                "predicted_mastery": _format_mastery_percent(raw_mastery),
                "mastery_status": mastery_status,
                "evidence": "-",
                "selection_bucket": item.get("selection_bucket", ""),
            }
        )
    return rows


def _format_mastery_percent(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    if abs(number - round(number)) < 0.005:
        return f"{int(round(number))}%"
    return f"{number:.2f}".rstrip("0").rstrip(".") + "%"


def _detect_risk_flags(initial_query: str, history_context: str) -> list[str]:
    text = f"{initial_query} {history_context}".lower()
    rules = {
        "安全风险": ["触电", "高压", "爆炸", "烧伤", "危险", "裸露电线", "中毒"],
        "伦理风险": ["虐待", "伤害动物", "伤人", "残害"],
        "规则风险": ["违法", "攻击", "武器", "破坏"],
    }
    flags = []
    for label, words in rules.items():
        if any(word in text for word in words):
            flags.append(label)
    return flags


def _context_anchor(context: dict[str, Any]) -> str:
    history_context = str(context.get("history_context") or "").strip()
    initial_query = str(context.get("initial_query") or "").strip()
    if history_context:
        return history_context
    if initial_query and initial_query != "未提供":
        return initial_query
    return "当前学习上下文"


def _build_theme_judgement(
    selected: list[dict[str, Any]],
    context: dict[str, Any],
    risk_flags: list[str],
) -> dict[str, Any]:
    topic_names = [item["topic_name"] for item in selected if item.get("topic_name")]
    domain_names = [item["domain_name"] for item in selected if item.get("domain_name")]
    topic = Counter(topic_names).most_common(1)[0][0] if topic_names else "当前上下文相关知识点"
    domains = [name for name, _ in Counter(domain_names).most_common(3)] or ["小学科学综合"]
    risk_text = "、".join(risk_flags) if risk_flags else "未见明显安全、伦理或规则风险"
    anchor = _context_anchor(context)
    text = (
        f"当前提供的学习上下文主要聚焦“{topic}”相关内容，"
        f"核心领域主要分布在 { '、'.join(domains) }。"
        f"本次诊断以“{anchor}”为主要依据，结合学习上下文与模型预测结果形成，风险判断为：{risk_text}。"
    )
    return {
        "theme": topic,
        "domains": domains,
        "risk_flags": risk_flags,
        "text": text,
        "initial_query": context["initial_query"],
        "history_context": context["history_context"],
    }


def _build_learning_analysis(
    selected: list[dict[str, Any]],
    mastery_rows: list[dict[str, Any]],
    risk_flags: list[str],
    context: dict[str, Any],
) -> dict[str, Any]:
    return _build_agent_learning_analysis_task(selected, mastery_rows, risk_flags, context)


def _build_agent_learning_analysis_task(
    selected: list[dict[str, Any]],
    mastery_rows: list[dict[str, Any]],
    risk_flags: list[str],
    context: dict[str, Any],
) -> dict[str, Any]:
    scores = [_row_score(row) for row in mastery_rows]
    avg_score = round(sum(scores) / len(scores)) if scores else None
    strong = [row for row in mastery_rows if _row_score(row) >= 70]
    middle = [row for row in mastery_rows if 40 <= _row_score(row) < 70]
    weak = [row for row in mastery_rows if _row_score(row) < 40]
    row_by_source_id = {int(row["source_skill_id"]): row for row in mastery_rows}
    strong_items = [item for item in selected if int(item["skill_id"]) in {int(row["source_skill_id"]) for row in strong}]
    middle_items = [item for item in selected if int(item["skill_id"]) in {int(row["source_skill_id"]) for row in middle}]
    weak_items = [item for item in selected if int(item["skill_id"]) in {int(row["source_skill_id"]) for row in weak}]
    anchor = _context_anchor(context)

    return {
        "mode": "agent_rewrite_required",
        "rewrite_scope": "只重写 ## 3. 学情分析结果 下的自然语言分析与教学建议；不要改动主题判定、知识点集合表、掌握度表和诊断知识点明细。",
        "context_anchor": anchor,
        "average_mastery_percent": avg_score,
        "risk_flags": risk_flags,
        "source_materials": {
            "history_summary": context.get("sequence_summary", {}),
            "strong_points": _analysis_points(strong_items, row_by_source_id, limit=6),
            "developing_points": _analysis_points(middle_items, row_by_source_id, limit=8),
            "weak_points": _analysis_points(weak_items, row_by_source_id, limit=8),
            "all_mastery_rows": [
                {
                    "knowledge_point_id": row["skill_id"],
                    "source_skill_id": row["source_skill_id"],
                    "knowledge_point_name": row["knowledge_point_name"],
                    "predicted_mastery": row["predicted_mastery"],
                    "mastery_status": row["mastery_status"],
                }
                for row in mastery_rows
            ],
            "selected_knowledge_points": [
                {
                    "knowledge_point_id": item["report_skill_id"],
                    "source_skill_id": int(item["skill_id"]),
                    "knowledge_point_name": item["knowledge_point_name"],
                    "knowledge_point_description": item.get("knowledge_point_description", ""),
                    "topic_name": item.get("topic_name", ""),
                    "type": item.get("type", ""),
                }
                for item in selected
            ],
        },
        "style_template": _learning_analysis_style_template(),
        "writing_requirements": [
            "使用自然、面向学生和老师都能读懂的中文分析，不要像字段拼接。",
            "必须基于 source_materials 中的 KT 预测、掌握状态、知识点描述和上下文，不要编造新的掌握度或知识点。",
            "自然语言分析的章节结构、语气和分析口径以 Markdown 模板为准，不要套用旧的小标题格式。",
            "可以参考 style_template 的结构和语气，但不要逐字套用模板，也不要输出模板原文。",
            "不要暴露内部选择数量、算法细节、n-gram、后端参数或模型字段来源。",
        ],
    }


def _row_score(row: dict[str, Any]) -> float:
    try:
        return float(str(row["predicted_mastery"]).rstrip("%"))
    except ValueError:
        return 0.0


def _analysis_points(
    items: list[dict[str, Any]],
    row_by_source_id: dict[int, dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    rows = []
    for item in items[:limit]:
        row = row_by_source_id.get(int(item["skill_id"]))
        if not row:
            continue
        rows.append(
            {
                "knowledge_point_id": row["skill_id"],
                "source_skill_id": row["source_skill_id"],
                "knowledge_point_name": row["knowledge_point_name"],
                "knowledge_point_description": item.get("knowledge_point_description", ""),
                "predicted_mastery": row["predicted_mastery"],
                "mastery_status": row["mastery_status"],
                "topic_name": item.get("topic_name", ""),
                "type": item.get("type", ""),
            }
        )
    return rows


def _learning_analysis_style_template() -> str:
    if _LEARNING_ANALYSIS_TEMPLATE_PATH.exists():
        return _LEARNING_ANALYSIS_TEMPLATE_PATH.read_text(encoding="utf-8").strip()
    return (
        "### 3.1 总体学情概述\n\n"
        "概括本次 KT 诊断覆盖的知识点范围、平均掌握水平和整体学习状态。\n\n"
        "### 3.2 优势知识点分析\n\n"
        "结合高掌握度或相对稳定的知识点，说明学生已有基础和可作为迁移支点的内容。\n\n"
        "### 3.3 薄弱模块诊断\n\n"
        "结合低掌握度和中等掌握度知识点，按模块说明主要短板、理解断点和后续学习风险。\n\n"
        "### 3.4 教学建议\n\n"
        "给出围绕薄弱模块补基础、典型题训练和持续追踪的建议。"
    )


def _selected_knowledge_points(selected: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "knowledge_point_id": item.get("report_skill_id"),
            "source_skill_id": int(item["skill_id"]),
            "knowledge_point_name": item.get("knowledge_point_name", ""),
            "knowledge_point_description": item.get("knowledge_point_description", ""),
            "type": item.get("type", ""),
            "topic_name": item.get("topic_name", ""),
        }
        for item in selected
    ]


def _model_label(model_info: dict[str, Any]) -> str:
    model_type = str(model_info.get("model_type") or "").strip()
    source_project = str(model_info.get("source_project") or "").strip()
    if source_project == "rekt" or model_type.startswith("rekt"):
        return "REKT 题目序列模型"
    if model_type:
        return model_type
    return "KT 模型"


def _build_analysis_process(
    context: dict[str, Any],
    selected: list[dict[str, Any]],
    model_info: dict[str, Any],
) -> dict[str, Any]:
    model_label = _model_label(model_info)
    return {
        "source_mode": context["trace_source"],
        "student_profile": context["student_profile"],
        "history_summary": context["sequence_summary"],
        "selection_preview": [
            {
                "skill_id": item["report_skill_id"],
                "source_skill_id": int(item["skill_id"]),
                "selection_score": round(float(item.get("selection_score", 0.0)), 4),
                "matched_terms": item.get("matched_terms", []),
            }
            for item in selected[:8]
        ],
        "process_steps": [
            "步骤1：读取学生历史作答与上下文信息。",
            f"步骤2：用 {model_label} 生成全部目标知识点的掌握概率。",
            "步骤3：根据当前学习上下文与知识点描述做相关性排序。",
            "步骤4：结合相关知识点的模型预测结果生成结构化学情分析。",
        ],
    }


def _render_report_markdown(
    *,
    theme_judgement: dict[str, Any],
    knowledge_points: list[dict[str, Any]],
    learning_analysis: dict[str, Any],
    mastery_rows: list[dict[str, Any]],
    analysis_process: dict[str, Any],
    selected_knowledge_points: list[dict[str, Any]],
) -> str:
    kp_lines = [
        "| 知识点ID | 知识点名称 | 类型 |",
        "|------------|------------|------|",
    ]
    for item in knowledge_points:
        kp_lines.append(
            f"| {item['knowledge_point_id']} | {_escape_cell(item['knowledge_point_name'])} | {item['type']} |"
        )

    mastery_lines = [
        "| 知识点ID | 知识点名称 | 预测掌握度 | 掌握状态 | 判断依据 |",
        "|------------|------------|------------|----------|----------|",
    ]
    for row in mastery_rows:
        mastery_lines.append(
            f"| {row['skill_id']} | {_escape_cell(row['knowledge_point_name'])} | {row['predicted_mastery']} | "
            f"{row['mastery_status']} | {_escape_cell(row['evidence'])} |"
        )

    rewrite_block = _agent_rewrite_placeholder(learning_analysis)

    return (
        "## 1. 主题判定\n\n"
        f"{theme_judgement['text']}\n\n"
        "## 2. 知识点集合\n\n"
        f"{chr(10).join(kp_lines)}\n\n"
        "## 3. 学情分析结果\n\n"
        "自然语言分析\n\n"
        f"{rewrite_block}\n\n"
        f"{chr(10).join(mastery_lines)}\n\n"
        "## 4. 诊断知识点明细\n\n"
        "```json\n"
        f"{json.dumps(selected_knowledge_points, ensure_ascii=False, indent=2)}\n"
        "```"
    )


def _agent_rewrite_placeholder(learning_analysis: dict[str, Any]) -> str:
    source_materials = learning_analysis.get("source_materials", {})
    weak_names = _point_names(source_materials.get("weak_points", []))
    developing_names = _point_names(source_materials.get("developing_points", []))
    strong_names = _point_names(source_materials.get("strong_points", []))
    style_template = str(learning_analysis.get("style_template") or "").strip()
    if not style_template:
        style_template = _learning_analysis_style_template()

    template_block = ""
    if style_template:
        template_block = (
            "\n参考模板如下。模板仅供参考，不要直接输出模板原文；"
            "模板内的示例数字、知识点名称和模块分布不能当作本次诊断事实。\n\n"
            "```markdown\n"
            f"{style_template}\n"
            "```\n"
        )

    return (
        "<!-- AGENT_REWRITE_REQUIRED_BEGIN -->\n"
        "调用方 Agent 请只替换本标记块，生成自然语言分析与教学建议；不要改动本报告的主题判定、知识点集合表、掌握度表和诊断知识点明细。\n\n"
        "输出硬约束：替换内容第一行必须是：`### 3.1 总体学情概述`。\n"
        "在 `### 3.1 总体学情概述` 之前不要输出任何文字、说明、标题、引导语或分隔线。\n"
        "不要输出类似“根据返回的 KT 诊断结果”“以下是替换后的自然语言分析与教学建议”“以上内容已生成”的说明性语句。\n\n"
        f"- 学习上下文：{learning_analysis.get('context_anchor', '当前学习上下文')}\n"
        f"- 平均预测掌握度：{learning_analysis.get('average_mastery_percent', '未提供')}%\n"
        f"- 历史作答摘要：{_history_summary_text(source_materials.get('history_summary', {}))}\n"
        f"- 高掌握度候选知识点：{strong_names or '无明显高分知识点'}\n"
        f"- 中等掌握度候选知识点：{developing_names or '无明显中等掌握知识点'}\n"
        f"- 低掌握度候选知识点：{weak_names or '无明显低分知识点'}\n"
        f"- 风险标记：{_risk_flags_text(learning_analysis.get('risk_flags', []))}\n\n"
        "自然语言分析模板：改写本占位块时必须参考 llm_analysis.agent_revision_task.style_template 中的结构、语气和分析口径；"
        "模板内的示例数字、知识点名称和模块分布只作为写法示例，不能当作本次诊断事实。\n"
        f"{template_block}"
        "请按上方 Markdown 模板的章节结构组织自然语言分析，并用本次 source_materials 中的真实数据替换模板示例内容；不要输出开场说明、分隔线或结尾说明，只输出可直接放入 ## 3. 学情分析结果 的正文。\n"
        "教学建议必须基于 llm_analysis.agent_revision_task.source_materials，不要编造掌握度或知识点。\n"
        "<!-- AGENT_REWRITE_REQUIRED_END -->"
    )


def _point_names(points: Any) -> str:
    if not isinstance(points, list):
        return ""
    names = []
    for point in points:
        if not isinstance(point, dict):
            continue
        name = point.get("knowledge_point_name")
        mastery = point.get("predicted_mastery")
        if name and mastery:
            names.append(f"{name}（{mastery}）")
        elif name:
            names.append(str(name))
    return "、".join(names)


def _history_summary_text(summary: Any) -> str:
    if not isinstance(summary, dict):
        return "未提供"
    return (
        f"历史长度 {summary.get('history_length', 0)}，"
        f"整体正确率 {_format_ratio(summary.get('accuracy', 0.0))}，"
        f"最近 {summary.get('recent_window', 0)} 次正确率 {_format_ratio(summary.get('recent_accuracy', 0.0))}"
    )


def _risk_flags_text(flags: Any) -> str:
    if isinstance(flags, list) and flags:
        return "、".join(str(flag) for flag in flags)
    return "未见明显安全、伦理或规则风险"


def _escape_cell(text: str) -> str:
    return str(text or "").replace("|", "\\|").replace("\n", " ").strip()


def _format_ratio(value: float | None) -> str:
    if value is None:
        return "未提供"
    return f"{round(float(value) * 100)}%"
