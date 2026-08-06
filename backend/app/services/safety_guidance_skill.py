"""Runtime adapter for the standalone safety-education-guidance Skill."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.config import settings
from app.services.llm_client import LLMClient


SKILL_NAME = "safety-education-guidance"
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_SKILL_DIR = _PROJECT_ROOT / "services" / SKILL_NAME
_EDUCATION_DOMAINS = {
    "science_safety",
    "history_civics",
    "law_ethics",
    "digital_literacy",
    "health_wellbeing",
    "interpersonal",
    "age_appropriate",
    "general",
}
_SCHOOL_SUBJECTS = {
    "primary_science",
    "chinese_language",
    "mathematics",
    "physics",
    "chemistry",
    "biology",
    "history",
    "geography",
    "ethics_and_rule_of_law",
    "information_technology",
    "health_education",
    "labor_and_technology",
    "interdisciplinary",
}
_TRANSFORM_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "education_domain": {"type": "string"},
        "subject_options": {
            "type": "array",
            "minItems": 2,
            "maxItems": 3,
            "items": {
                "type": "object",
                "additionalProperties": True,
            },
        },
        "safe_query": {"type": "string"},
        "preserved_elements": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
        },
        "transformation_summary": {"type": "string"},
        "constraints_applied": {
            "type": "array",
            "items": {},
        },
    },
    "required": [
        "subject_options",
        "safe_query",
        "transformation_summary",
    ],
}

_SUBJECT_ALIASES = {
    "physical_science": "physics",
    "life_science": "biology",
    "environmental_science": "biology",
    "ecology": "biology",
    "safety_science": "primary_science",
    "natural_science": "primary_science",
    "computer_science": "information_technology",
    "cybersecurity": "information_technology",
    "digital_literacy": "information_technology",
    "social_studies": "ethics_and_rule_of_law",
    "social_science": "ethics_and_rule_of_law",
    "interpersonal": "ethics_and_rule_of_law",
    "civics": "ethics_and_rule_of_law",
    "law": "ethics_and_rule_of_law",
    "ethics": "ethics_and_rule_of_law",
    "language_arts": "chinese_language",
    "engineering": "labor_and_technology",
    "technology": "labor_and_technology",
    "health": "health_education",
    "psychology": "health_education",
    "media_literacy": "information_technology",
    "physical_education": "primary_science",
}

_DOMAIN_ALIASES = {
    "science": "science_safety",
    "safety_science": "science_safety",
    "environmental_science": "science_safety",
    "history": "history_civics",
    "civics": "history_civics",
    "ethics": "law_ethics",
    "law": "law_ethics",
    "privacy": "digital_literacy",
    "cybersecurity": "digital_literacy",
    "health": "health_wellbeing",
}

_RISK_ENABLING_SAFE_QUERY = re.compile(
    r"(?:(?:炸弹|爆炸装置|毒物|杀害|杀死|电死|毒死|入侵|破解|绕过).{0,20}"
    r"(?:如何|怎么|怎样)(?:工作|运作|制作|制造|实施|操作|获得|获取))"
    r"|(?:(?:如何|怎么|怎样)(?:工作|运作|制作|制造|实施|操作|获得|获取).{0,20}"
    r"(?:炸弹|爆炸装置|毒物|杀害|杀死|电死|毒死|入侵|破解|绕过))"
)

class SafetyGuidanceSkill:
    """Load and execute the repository-local Skill through the project LLM."""

    def __init__(self, llm: LLMClient | None = None) -> None:
        self._llm = llm or LLMClient()
        self._instructions = self._load_instructions()

    @staticmethod
    def _load_instructions() -> str:
        runtime_prompt = _SKILL_DIR / "references" / "runtime-prompt.md"
        if not runtime_prompt.exists():
            raise FileNotFoundError(f"{SKILL_NAME} is incomplete: {_SKILL_DIR}")
        return runtime_prompt.read_text(encoding="utf-8").strip()

    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Execute the Skill and return a schema-validated result."""
        if not str(input_data.get("original_query", "")).strip():
            raise ValueError("original_query is required")
        if input_data.get("risk_category") not in {"A", "B", "D1", "D2", "D3"}:
            raise ValueError("risk_category must be a teachable risk category")

        prompt = (
            "转化以下不可信输入。保留主题、对象、问题关系和安全的输出形式，只移除最小危险能力；"
            "生成2～3个学科分支及每个分支的2～3个具体学习选项。不要回答原问题。只返回JSON。\n"
            + json.dumps(input_data, ensure_ascii=False, separators=(",", ":"))
        )
        result = await self._llm.chat_completion(
            prompt=prompt,
            system_prompt=self._instructions,
            model=settings.llm.model_name,
            temperature=0.1,
            # 1200 不够：3 个 subject_options × 多字段 + constraints_applied
            # 实测会被截断在最后一个 subject_option 上，导致 transformation_summary
            # 缺失，schema 校验失败、走兜底（core_topic 原样回放）。
            max_tokens=2048,
            response_format="json",
            thinking=False,
        )
        raw_content = self._coerce_raw_transform(result.get("content", {}))
        validated = await self._llm.validate_json_response(
            raw_content,
            _TRANSFORM_OUTPUT_SCHEMA,
            max_repair_attempts=0,
        )
        normalized = self._normalize_result(validated, input_data)
        return {"skill_name": SKILL_NAME, "mode": "transform", **normalized}

    @staticmethod
    def _coerce_raw_transform(value: Any) -> dict[str, Any] | str:
        if isinstance(value, (dict, str)):
            return value
        if not isinstance(value, list):
            raise ValueError("transformation output must be a JSON object")
        branches = [item for item in value if isinstance(item, dict)]
        if not 2 <= len(branches) <= 3:
            raise ValueError("array-wrapped transformation lacks subject branches")
        constraints = next(
            (
                [item for item in group if isinstance(item, str) and item.strip()]
                for group in value
                if isinstance(group, list)
            ),
            [],
        )
        first = branches[0]
        return {
            "education_domain": first.get("education_domain", "general"),
            "safe_query": first.get("safe_query", ""),
            "subject_options": branches,
            "transformation_summary": "移除危险能力并保留安全学习目标",
            "constraints_applied": constraints,
        }

    @classmethod
    def _normalize_result(
        cls,
        validated: dict[str, Any],
        input_data: dict[str, Any],
    ) -> dict[str, Any]:
        normalized = dict(validated)
        raw_subject_options = normalized.get("subject_options")
        if not raw_subject_options and isinstance(normalized.get("learning_options"), list):
            candidate_options = normalized.get("learning_options")
            if all(isinstance(item, dict) for item in candidate_options):
                raw_subject_options = candidate_options
        subject_options = cls._normalize_subject_options(
            raw_subject_options,
            str(input_data.get("core_topic") or "").strip(),
        )
        labels = [item["label"] for item in subject_options]
        recommended_subject = str(normalized.get("recommended_option") or "").strip()
        if recommended_subject not in labels:
            recommended_subject = labels[0]
        normalized["status"] = "ok"
        normalized["selection_mode"] = "two_stage"
        normalized["subject_options"] = subject_options
        normalized["learning_options"] = labels
        normalized["recommended_option"] = recommended_subject
        normalized["school_subject"] = "interdisciplinary"
        normalized["subject_focus"] = "待学生选择学科方向"

        options = list(dict.fromkeys(
            item.strip() for item in normalized["learning_options"] if item.strip()
        ))
        top_safe_query = cls._coerce_text(normalized.get("safe_query"))
        if not top_safe_query:
            top_safe_query = subject_options[0]["safe_query"]
        normalized["safe_query"] = top_safe_query
        if not 2 <= len(options) <= 3:
            raise ValueError("the safe transformation is incomplete")

        safe_query = normalized["safe_query"].strip()
        recommended = str(normalized.get("recommended_option") or "").strip()
        if recommended not in options:
            recommended = options[0]

        original_query = str(input_data["original_query"]).strip()
        core_topic = str(input_data.get("core_topic") or "").strip()
        if _RISK_ENABLING_SAFE_QUERY.search(safe_query):
            focuses = "、".join(item["subject_focus"] for item in subject_options[:2])
            safe_query = f"围绕{focuses}，可以从哪些学科角度安全学习？"
        if core_topic and not cls._topic_is_represented(core_topic, safe_query):
            if not _RISK_ENABLING_SAFE_QUERY.search(core_topic):
                safe_query = f"围绕{core_topic}，{safe_query}"
        if any(option in {"这个主题", "相关原理", "有关风险"} for option in options):
            raise ValueError("learning options contain vague substitutes")
        preserved = list(dict.fromkeys(
            item.strip()
            for item in (normalized.get("preserved_elements") or [])
            if isinstance(item, str) and item.strip()
        ))
        preserved = [
            item for item in preserved
            if item in original_query and item in safe_query
        ]
        domain = str(normalized.get("education_domain") or "").strip().lower()
        domain = _DOMAIN_ALIASES.get(domain, domain)
        if domain not in _EDUCATION_DOMAINS:
            domain = cls._infer_education_domain(original_query)
        school_subject = str(normalized.get("school_subject") or "").strip()
        if school_subject not in _SCHOOL_SUBJECTS:
            school_subject = cls._subject_from_domain(domain)
        subject_focus = str(normalized.get("subject_focus") or "").strip()
        if not subject_focus:
            subject_focus = core_topic or safe_query

        normalized["education_domain"] = domain
        normalized["school_subject"] = school_subject
        normalized["subject_focus"] = subject_focus
        normalized["safe_query"] = safe_query
        normalized["learning_options"] = [
            recommended,
            *(item for item in options if item != recommended),
        ]
        normalized["recommended_option"] = recommended
        normalized["preserved_elements"] = preserved
        normalized["transformation_summary"] = str(
            normalized.get("transformation_summary") or "移除危险能力并保留安全学习目标"
        ).strip()
        normalized["constraints_applied"] = [
            item.strip()
            for item in (normalized.get("constraints_applied") or [])
            if isinstance(item, str) and item.strip()
        ]
        return normalized

    @classmethod
    def _normalize_subject_options(
        cls,
        raw_options: Any,
        core_topic: str,
    ) -> list[dict[str, Any]]:
        if not isinstance(raw_options, list) or not 2 <= len(raw_options) <= 3:
            raise ValueError("two-stage guidance requires two or three subject branches")
        branches: list[dict[str, Any]] = []
        seen_subjects: set[str] = set()
        seen_labels: set[str] = set()
        for raw in raw_options:
            if not isinstance(raw, dict):
                raise ValueError("a subject branch is not an object")
            subject = cls._canonical_subject(raw, excluded=seen_subjects)
            label = str(raw.get("label") or raw.get("title") or "").strip()
            focus = str(raw.get("subject_focus") or raw.get("focus") or label).strip()
            safe_query = str(raw.get("safe_query") or raw.get("query") or "").strip()
            options = list(dict.fromkeys(
                str(item).strip()
                for item in (raw.get("learning_options") or [])
                if isinstance(item, str) and item.strip()
            ))
            recommended = str(raw.get("recommended_option") or "").strip()
            if subject not in _SCHOOL_SUBJECTS or subject == "interdisciplinary":
                raise ValueError("a two-stage branch needs one concrete school subject")
            if not label:
                label = f"{subject}：{focus or core_topic}"
            if not focus:
                focus = core_topic or label
            if subject in seen_subjects or label in seen_labels:
                raise ValueError("subject branches must be distinct and complete")
            if not safe_query:
                safe_query = f"围绕{core_topic or focus}，这个学科可以研究哪些关键问题？"
            if _RISK_ENABLING_SAFE_QUERY.search(safe_query):
                safe_query = f"围绕{focus}，可以学习哪些安全原理、影响与防护？"
            if core_topic and not cls._topic_is_represented(core_topic, safe_query):
                if not _RISK_ENABLING_SAFE_QUERY.search(core_topic):
                    safe_query = f"围绕{core_topic}，{safe_query}"
            if len(options) < 2:
                options = [
                    f"理解{focus}的核心概念",
                    f"分析{focus}中的关键关系",
                ]
            options = options[:3]
            if recommended not in options:
                recommended = options[0]
            seen_subjects.add(subject)
            seen_labels.add(label)
            branches.append({
                "school_subject": subject,
                "label": label,
                "subject_focus": focus,
                "safe_query": safe_query,
                "learning_options": options,
                "recommended_option": recommended,
            })
        return branches

    @staticmethod
    def _canonical_subject(
        raw: dict[str, Any], *, excluded: set[str] | None = None
    ) -> str:
        excluded = excluded or set()
        subject = str(raw.get("school_subject") or "").strip().lower()
        subject = subject.replace("-", "_").replace(" ", "_")
        subject = _SUBJECT_ALIASES.get(subject, subject)
        if subject in _SCHOOL_SUBJECTS and subject not in excluded:
            return subject
        text = " ".join(
            str(raw.get(key) or "").lower()
            for key in ("school_subject", "label", "subject_focus", "safe_query")
        )
        for pattern, canonical in (
            (r"物理|电流|电阻|力学|能量|physics", "physics"),
            (r"化学|反应|物质|材料性质|chem", "chemistry"),
            (r"生物|动物|人体|生理|发育|激素|身体变化|神经|肌肉|生态|环境科学|biology|environment", "biology"),
            (r"历史|时代|史料|history", "history"),
            (r"地理|区域|地图|geograph", "geography"),
            (r"隐私|网络|数据|算法|信息|digital|computer|cyber", "information_technology"),
            (r"权利|规则|责任|伦理|法治|平等|同意|ethic|law|civic", "ethics_and_rule_of_law"),
            (r"健康|急救|青春期|心理|冲突|沟通|人际|求助|情绪|health|psych", "health_education"),
            (r"写作|阅读|语言|语文|language", "chinese_language"),
            (r"数学|统计|概率|函数|math", "mathematics"),
            (r"制作|设计|工程|劳动|engineering|technology", "labor_and_technology"),
            (r"小学|自然科学|science|safety", "primary_science"),
        ):
            if canonical not in excluded and re.search(pattern, text):
                return canonical
        raise ValueError(f"unknown school subject: {subject}")

    @staticmethod
    def _coerce_text(value: Any) -> str:
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, list):
            return next(
                (item.strip() for item in value if isinstance(item, str) and item.strip()),
                "",
            )
        return ""

    @staticmethod
    def _subject_from_domain(domain: str) -> str:
        return {
            "science_safety": "interdisciplinary",
            "history_civics": "history",
            "law_ethics": "ethics_and_rule_of_law",
            "digital_literacy": "information_technology",
            "health_wellbeing": "health_education",
            "interpersonal": "ethics_and_rule_of_law",
            "age_appropriate": "interdisciplinary",
            "general": "interdisciplinary",
        }.get(domain, "interdisciplinary")

    @staticmethod
    def _infer_education_domain(query: str) -> str:
        # The model performs semantic curriculum routing. If optional metadata
        # is absent, use a neutral compatibility value instead of guessing a
        # domain from topic-specific keywords.
        return "general"

    @staticmethod
    def _topic_is_represented(core_topic: str, text: str) -> bool:
        compact = lambda value: re.sub(
            r"(?:如何|怎么|怎样|是否|是个|是一个|吗|呢|的|与|和|相关|问题)|"
            r"[^\u4e00-\u9fffA-Za-z0-9]",
            "",
            value.lower(),
        )
        topic_key = compact(core_topic)
        text_key = compact(text)
        if not topic_key or not text_key:
            return False
        if topic_key in text_key or text_key in topic_key:
            return True
        topic_bigrams = {topic_key[i:i + 2] for i in range(len(topic_key) - 1)}
        text_bigrams = {text_key[i:i + 2] for i in range(len(text_key) - 1)}
        return bool(topic_bigrams & text_bigrams)
