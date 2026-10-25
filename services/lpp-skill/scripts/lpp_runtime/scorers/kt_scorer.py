"""KT 打分器：包装 kt-runtime-skill 的 KT 模型和数据加载逻辑。

不复制 KT 引擎代码——直接引用 `kt-runtime-skill` 里的现成实现（数据加载、
模型定义、checkpoint 加载），保证 KT 只有一份权威实现，改 bug/加功能只用
改一个地方。
"""

from __future__ import annotations

import os
import sys
import warnings
import json
from pathlib import Path

import torch

# kt-runtime-skill 的位置可以用环境变量覆盖，默认取 SmartTutor 内的兄弟服务。
def default_kt_runtime_skill_root() -> Path:
    return Path(__file__).resolve().parents[4] / "kt-runtime-skill"


KT_RUNTIME_SKILL_ROOT = Path(
    os.environ.get(
        "KT_RUNTIME_SKILL_ROOT",
        str(default_kt_runtime_skill_root()),
    )
)
_SCRIPTS_DIR = KT_RUNTIME_SKILL_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from kt_runtime.kt_engine.config import KTConfig  # noqa: E402
from kt_runtime.kt_engine.data import KTDataBundle, load_kt_data  # noqa: E402
from kt_runtime.kt_engine.model import KT  # noqa: E402


class KTScorer:
    """基于 kt-runtime-skill 里已训练好的 KT 模型实现的 KTScorer。"""

    def __init__(self, config: KTConfig | None = None):
        self.config = config or KTConfig.from_env()
        self._device = self._resolve_device(self.config.device, self.config.allow_cpu_fallback)
        self.data: KTDataBundle = load_kt_data(self.config.data_dir)
        self._question_metadata = self._load_question_metadata()
        self._knowledge_metadata = self._load_knowledge_metadata()
        self._knowledge_by_topic = self._index_knowledge_by_topic()
        self.model = self._load_model()
        self._primary_skill = torch.as_tensor(
            self.data.question_primary_skill, device=self._device, dtype=torch.long
        )

    @staticmethod
    def _resolve_device(device_name: str, allow_cpu_fallback: bool) -> torch.device:
        requested = torch.device(device_name)
        if requested.type == "cuda" and not torch.cuda.is_available():
            if not allow_cpu_fallback:
                raise RuntimeError(f"CUDA device requested but unavailable: {device_name}")
            warnings.warn(f"CUDA unavailable; falling back from {device_name} to cpu", RuntimeWarning)
            return torch.device("cpu")
        return requested

    def _load_model(self) -> KT:
        model = KT(
            qst_num=self.data.qst_num,
            skl_num=self.data.skl_num,
            max_seq_len=self.config.max_seq_len,
            d=self.config.hidden_dim,
            dropout=self.config.dropout,
        ).to(self._device)

        checkpoint = torch.load(self.config.checkpoint_path, map_location=self._device, weights_only=False)
        state_dict = (
            checkpoint["state_dict"]
            if isinstance(checkpoint, dict) and "state_dict" in checkpoint
            else checkpoint
        )
        model.load_state_dict(state_dict)
        model.eval()
        return model

    @property
    def device(self) -> torch.device:
        return self._device

    @property
    def question_universe_size(self) -> int:
        return self.data.qst_num

    def skills_of(self, question_id: int) -> list[int]:
        return list(self.data.question_to_skills.get(int(question_id), []))

    def questions_of_skill(self, skill_id: int) -> list[int]:
        return list(self.data.skill_to_questions.get(int(skill_id), []))

    def question_metadata(self, question_id: int) -> dict[str, object]:
        """返回展示给学生的题目信息，题库缺失时提供可读的兜底内容。"""
        question_id = int(question_id)
        return self._question_metadata.get(
            question_id,
            {
                "question_id": question_id,
                "question_desc": f"题目 {question_id}",
                "type": "练习题",
                "difficulty": None,
                "grade": None,
            },
        )

    def knowledge_metadata(self, skill_id: int) -> dict[str, object]:
        """返回知识点目录中的教学描述与课程顺序信息。"""
        skill_id = int(skill_id)
        return self._knowledge_metadata.get(
            skill_id,
            {
                "knowledge_point_id": skill_id,
                "knowledge_point_name": self.data.skill_names.get(skill_id, f"知识点{skill_id}"),
                "knowledge_point_description": None,
                "grade_name": None,
                "grade_order": None,
                "topic_id": None,
                "sequence": None,
                "sequence_label": None,
            },
        )

    def knowledge_sequence(self, skill_id: int) -> dict[str, object]:
        """按同年级、同主题内的 ``seq`` 返回相邻前后序知识点。"""
        current = self.knowledge_metadata(skill_id)
        grade_order = current.get("grade_order")
        topic_id = current.get("topic_id")
        if grade_order is None or topic_id is None:
            return {"previous": None, "next": None}

        knowledge_points = self._knowledge_by_topic.get((int(grade_order), int(topic_id)), [])
        current_index = next(
            (
                index
                for index, item in enumerate(knowledge_points)
                if item["knowledge_point_id"] == int(skill_id)
            ),
            None,
        )
        if current_index is None:
            return {"previous": None, "next": None}
        return {
            "previous": knowledge_points[current_index - 1] if current_index > 0 else None,
            "next": (
                knowledge_points[current_index + 1]
                if current_index + 1 < len(knowledge_points)
                else None
            ),
        }

    def _load_question_metadata(self) -> dict[int, dict[str, object]]:
        """单独读取题干元数据，不修改 kt-runtime-skill 的权威数据加载接口。"""
        metadata: dict[int, dict[str, object]] = {}
        exercise_info_path = self.config.data_dir / "exercise_info.json"
        with exercise_info_path.open(encoding="utf-8") as file:
            for line in file:
                item = json.loads(line)
                metadata[int(item["question_id"])] = item
        return metadata

    def _load_knowledge_metadata(self) -> dict[int, dict[str, object]]:
        """读取知识点目录；该目录是前后序信息的权威来源。"""
        metadata: dict[int, dict[str, object]] = {}
        knowledge_path = self.config.data_dir / "knowledges.json"
        with knowledge_path.open(encoding="utf-8") as file:
            for item in json.load(file):
                skill_id = int(item["id"])
                metadata[skill_id] = {
                    "knowledge_point_id": skill_id,
                    "knowledge_point_name": str(item["name"]),
                    "knowledge_point_description": item.get("description"),
                    "grade_name": item.get("grade_name"),
                    "grade_order": int(item["grade_order"]) if item.get("grade_order") is not None else None,
                    "topic_id": int(item["topic_id"]) if item.get("topic_id") is not None else None,
                    "sequence": int(item["seq"]) if item.get("seq") is not None else None,
                    "sequence_label": item.get("seq_char"),
                }
        return metadata

    def _index_knowledge_by_topic(self) -> dict[tuple[int, int], list[dict[str, object]]]:
        """建立 ``(grade_order, topic_id) -> 按 seq 排序的知识点`` 索引。"""
        indexed: dict[tuple[int, int], list[dict[str, object]]] = {}
        for item in self._knowledge_metadata.values():
            grade_order = item.get("grade_order")
            topic_id = item.get("topic_id")
            sequence = item.get("sequence")
            if grade_order is None or topic_id is None or sequence is None:
                continue
            indexed.setdefault((int(grade_order), int(topic_id)), []).append(item)
        for knowledge_points in indexed.values():
            knowledge_points.sort(
                key=lambda item: (int(item["sequence"]), int(item["knowledge_point_id"]))
            )
        return indexed

    def forward_batch(
        self, hist_q: torch.Tensor, hist_a: torch.Tensor, next_q: torch.Tensor
    ) -> torch.Tensor:
        """把 DSMOEA 风格的 (hist_q, hist_a, next_q) 转成 KT 需要的输入。

        KT 是自回归模型：每一步的预测依赖之前所有步骤累积的状态，因此需要把
        "已发生的历史"(hist_q/hist_a) 和"本次要评估的新候选题目"
        (next_q 的最后一位) 拼接成一条完整的交互链，再整体喂给 KT。

        `next_q` 除最后一位外的其余位置在 DSMOEA 的调用惯例里只是占位
        （调用方只读取输出的最后一位），这里不需要用到。
        """
        device = self._device
        target_q = next_q[:, -1:].to(device).long()
        merged_q = torch.cat([hist_q.to(device).long(), target_q], dim=1)

        # 新增位置的答案不影响它自己这一步的预测结果——KT 先用之前的状态
        # 预测当前题目，然后才用当前题目的答案去更新状态；由于这是序列里的
        # 最后一位，之后不会再有人读取被更新之后的状态，占位成 0 即可。
        pad_ans = torch.zeros_like(target_q)
        merged_a = torch.cat([hist_a.to(device).long(), pad_ans], dim=1)

        merged_skill = self._primary_skill[merged_q]

        # `last_problem` 参数在 KT.forward 内部只用来取 shape，从不参与实际
        # 计算（详见 kt-runtime-skill 的 model.py），占位即可。
        dummy_last = torch.zeros_like(merged_q)

        with torch.inference_mode():
            return self.model(dummy_last, merged_q, merged_skill, merged_a)
