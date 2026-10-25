"""基于 kt-runtime-skill KT 数据集的学生历史数据提供者。"""

from __future__ import annotations

from lpp_runtime.data.base import StudentHistory
from lpp_runtime.scorers.kt_scorer import KTScorer


class KTHistoryProvider:
    """从 KT 数据（`student_record.json`）读取学生历史。

    复用 `KTScorer` 已经加载好的 `KTDataBundle`，避免重复解析一遍数据文件。
    """

    def __init__(self, scorer: KTScorer):
        self._scorer = scorer

    def get_history(self, student_id: str):
        uid = int(student_id)
        recordings = self._scorer.data.recordings_by_user
        if uid not in recordings:
            raise KeyError(f"student_id {student_id} not found in KT recordings")
        rows = recordings[uid]  # 每行是 [question_id, response, mask]
        return StudentHistory(
            student_id=str(uid),
            question_ids=[int(r[0]) for r in rows],
            is_corrects=[int(r[1]) for r in rows],
        )

    def iter_student_ids(self):
        return (str(uid) for uid in self._scorer.data.recordings_by_user)
