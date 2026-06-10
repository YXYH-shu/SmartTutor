"""REKT 工具边界使用的数据结构。"""

from dataclasses import asdict, dataclass
from typing import Dict, List


@dataclass(frozen=True)
class StudentInteraction:
    """一条学生历史做题交互。"""

    exercise_id: int
    response: int


@dataclass(frozen=True)
class SkillMastery:
    """单个知识点/概念的掌握度估计。"""

    skill_id: int
    knowledge_state: float


@dataclass(frozen=True)
class DiagnosisResult:
    """REKT 工具服务返回的结构化诊断结果。"""

    user_id: int
    history_limit: int
    interactions: List[StudentInteraction]
    skills: List[SkillMastery]

    def to_dict(self) -> Dict:
        """转换为可 JSON 序列化的字典。"""
        return asdict(self)
