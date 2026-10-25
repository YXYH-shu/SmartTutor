"""学生历史数据的抽象接口（端口）。

搜索主流程通过这个接口读取"某个学生的历史做题序列"，不关心底层数据到底存成
KT 的 JSON Lines 格式，还是 DSMOEA 的 train_test/*.txt 格式。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol, runtime_checkable


@dataclass(frozen=True)
class StudentHistory:
    """一个学生的历史做题序列（按时间顺序）。"""

    student_id: str
    question_ids: list[int]
    is_corrects: list[int]

    def __post_init__(self) -> None:
        if len(self.question_ids) != len(self.is_corrects):
            raise ValueError(
                "question_ids 和 is_corrects 长度必须一致："
                f"{len(self.question_ids)} != {len(self.is_corrects)}"
            )


@runtime_checkable
class StudentHistoryProvider(Protocol):
    """统一的学生历史数据接口。"""

    def get_history(self, student_id: str) -> StudentHistory:
        """返回指定学生的历史做题序列。找不到该学生时抛 KeyError。"""
        ...

    def iter_student_ids(self) -> Iterable[str]:
        """遍历数据源里所有学生 id（用于批量扫描/评测场景）。"""
        ...
