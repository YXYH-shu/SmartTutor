"""基于 kt-runtime-skill REKT 数据集的学生历史数据提供者。"""

from __future__ import annotations

from lpp_runtime.data.base import StudentHistory
from lpp_runtime.scorers.rekt_scorer import RektScorer


class RektHistoryProvider:
    """从 REKT 数据（`student_record.json`）读取学生历史。

    复用 `RektScorer` 已经加载好的 `ReKTDataBundle`，避免重复解析一遍数据文件。
    """

    def __init__(self, scorer: RektScorer):
        self._scorer = scorer

    def get_history(self, student_id: str):
        uid = int(student_id)
        recordings = self._scorer.data.recordings_by_user
        if uid not in recordings:
            raise KeyError(f"student_id {student_id} not found in REKT recordings")
        rows = recordings[uid]  # 每行是 [question_id, response, mask]
        return StudentHistory(
            student_id=str(uid),
            question_ids=[int(r[0]) for r in rows],
            is_corrects=[int(r[1]) for r in rows],
        )

    def iter_student_ids(self):
        return (str(uid) for uid in self._scorer.data.recordings_by_user)
