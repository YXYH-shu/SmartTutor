"""将 KT 封装为 ITS 工具模型服务。"""

from pathlib import Path
from typing import Iterable, List, Optional
import warnings

import torch

try:
    from .config import KTConfig
    from .data import KTDataBundle, load_kt_data
    from .model import KT
    from .schemas import DiagnosisResult, SkillMastery, StudentInteraction
except ImportError:
    from config import KTConfig
    from data import KTDataBundle, load_kt_data
    from model import KT
    from schemas import DiagnosisResult, SkillMastery, StudentInteraction


class KTDiagnoser:
    """加载一次 KT，并对外提供结构化学生诊断方法。"""

    def __init__(self, config: Optional[KTConfig] = None) -> None:
        # 服务对象持有数据和模型，避免每次工具调用都重复加载权重。
        self.config = config or KTConfig.from_env()
        self.device = self._resolve_device(self.config.device, self.config.allow_cpu_fallback)
        self.data = load_kt_data(self.config.data_dir)
        self.model = self._load_model(self.data, self.config.checkpoint_path)

    @staticmethod
    def _resolve_device(device_name: str, allow_cpu_fallback: bool) -> torch.device:
        """解析 CUDA/CPU 设备；本地无 CUDA 时允许回退 CPU。"""
        requested = torch.device(device_name)
        if requested.type == "cuda" and not torch.cuda.is_available():
            if not allow_cpu_fallback:
                raise RuntimeError(f"CUDA device requested but unavailable: {device_name}")
            warnings.warn(f"CUDA unavailable; falling back from {device_name} to cpu", RuntimeWarning)
            return torch.device("cpu")
        return requested

    def _load_model(self, data: KTDataBundle, checkpoint_path: Path) -> KT:
        """实例化 KT，并兼容 raw state_dict 与训练脚本保存的 checkpoint dict。"""
        model = KT(
            qst_num=data.qst_num,
            skl_num=data.skl_num,
            max_seq_len=self.config.max_seq_len,
            d=self.config.hidden_dim,
            dropout=self.config.dropout,
        ).to(self.device)

        checkpoint = torch.load(checkpoint_path, map_location=self.device)
        state_dict = checkpoint["state_dict"] if isinstance(checkpoint, dict) and "state_dict" in checkpoint else checkpoint
        model.load_state_dict(state_dict)
        model.eval()
        return model

    def diagnose_user(
        self,
        user_id: int | str,
        history_limit: Optional[int] = None,
        skill_id: str | int | Iterable[int] = "local",
    ) -> DiagnosisResult:
        """估计指定学生的知识点掌握概率。

        skill_id 支持三种语义：
        - "all"：诊断数据集中全部知识点；
        - "local"：诊断历史窗口中出现过的题目关联知识点；
        - 具体 id 或 id 列表：只诊断目标知识点。
        """
        uid = int(user_id)
        limit = history_limit or self.config.history_limit
        if uid not in self.data.recordings_by_user:
            raise KeyError(f"user_id {uid} not found in KT recordings")

        # 默认使用前 history_limit 条交互，保持 raw 原型的“前 30 条记录”设定。
        history = self.data.recordings_by_user[uid][:limit]
        target_skills = self._target_skills(history, skill_id)
        skill_mastery = self._predict_skill_mastery(history, target_skills)

        # 输出层只暴露题目和答题结果，不把内部 mask 泄漏给上层智能体。
        interactions = [
            StudentInteraction(exercise_id=int(qid), response=int(resp))
            for qid, resp, _ in history
        ]
        skills = [
            SkillMastery(skill_id=skill_id, knowledge_state=skill_mastery[skill_id])
            for skill_id in sorted(skill_mastery)
        ]
        return DiagnosisResult(
            user_id=uid,
            history_limit=limit,
            interactions=interactions,
            skills=skills,
        )

    def _target_skills(
        self,
        history: List[List[int]],
        skill_id: str | int | Iterable[int],
    ) -> List[int]:
        """确定需要诊断的知识点集合。"""
        if isinstance(skill_id, str):
            selector = skill_id.strip().lower()
            if selector == "all":
                return sorted(self.data.skill_to_questions)
            if selector in {"", "local"}:
                return self._local_skills(history)
            return sorted({int(item.strip()) for item in selector.split(",") if item.strip()})

        if isinstance(skill_id, int):
            return [int(skill_id)]

        return sorted({int(item) for item in skill_id})

    def _local_skills(self, history: List[List[int]]) -> List[int]:
        """返回当前历史窗口中出现过的题目关联知识点。"""
        skills = set()
        for qid, _, _ in history:
            skills.update(self.data.question_to_skills.get(int(qid), []))
        return sorted(skills)

    def _predict_skill_mastery(self, history: List[List[int]], target_skill_ids: List[int]) -> dict[int, float]:
        """批量构造“下一题预测”，并按知识点聚合掌握概率。"""
        if not history or not target_skill_ids:
            return {skill_id: 0.0 for skill_id in target_skill_ids}

        # 对每个目标知识点，取出其关联题目；随后对这些题目做下一题预测。
        qst_list: List[int] = []
        idx_list: List[int] = []
        for skill_id in target_skill_ids:
            questions = self.data.skill_to_questions.get(skill_id, [])
            qst_list.extend(questions)
            idx_list.extend([skill_id] * len(questions))

        if not qst_list:
            return {skill_id: 0.0 for skill_id in target_skill_ids}

        with torch.no_grad():
            # 将同一段历史复制多份，每份追加一个待预测题目。
            history_tensor = torch.tensor([history], dtype=torch.long, device=self.device)
            qst_tensor = torch.tensor(qst_list, dtype=torch.long, device=self.device)
            one = torch.ones_like(qst_tensor)
            query_rows = torch.stack((qst_tensor, one, one), dim=1)

            expanded_history = history_tensor.repeat(query_rows.shape[0], 1, 1)
            seqs = torch.cat((expanded_history, query_rows.unsqueeze(1)), dim=1)

            # KT 输入为错位序列：cur_* 是历史位置，nxt_* 是下一时刻位置。
            cur_qst = seqs[:, :-1, 0]
            nxt_qst = seqs[:, 1:, 0]
            nxt_rst = seqs[:, 1:, 1]
            qst_skl = torch.tensor(self.data.question_primary_skill, dtype=torch.long, device=self.device)
            nxt_skl = qst_skl[nxt_qst]

            pred = self.model(cur_qst, nxt_qst, nxt_skl, nxt_rst)
            # 只取追加题目的最后一个预测位置作为掌握度估计。
            last_pred = pred[:, -1]

            # 一个知识点可能对应多道题，取这些题目预测概率的平均值。
            idx_tensor = torch.tensor(idx_list, dtype=torch.long, device=self.device)
            result = {}
            for skill_id in target_skill_ids:
                mask = idx_tensor == skill_id
                result[skill_id] = last_pred[mask].mean().item() if mask.any() else 0.0
            return result
