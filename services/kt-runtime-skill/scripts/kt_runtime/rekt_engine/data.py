"""REKT 数据加载工具。"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List
import json

import numpy as np


def parse_skill_ids(value) -> List[int]:
    """将单知识点或多知识点字段统一解析为知识点 id 列表。"""
    if isinstance(value, list):
        return [int(skill_id) for skill_id in value]
    return [int(value)]


@dataclass(frozen=True)
class ReKTDataBundle:
    """推理和训练都会用到的数据结构集合。"""

    qst_num: int
    usr_num: int
    skl_num: int
    question_to_skills: Dict[int, List[int]]
    question_primary_skill: np.ndarray
    skill_to_questions: Dict[int, List[int]]
    skill_names: Dict[int, str]
    recordings_by_user: Dict[int, List[List[int]]]


def load_rekt_data(data_dir: Path | str) -> ReKTDataBundle:
    """从 REKT 数据目录读取题目、知识点和学生行为序列。"""
    data_dir = Path(data_dir)
    question_to_skills: Dict[int, List[int]] = {}
    skill_to_questions: Dict[int, List[int]] = {}
    skill_names: Dict[int, str] = {}

    # 读取题目信息，构建“题目 -> 知识点”和“知识点 -> 题目”双向索引。
    with (data_dir / "exercise_info.json").open(encoding="utf-8") as file:
        for line in file:
            item = json.loads(line)
            qid = int(item["question_id"])
            skill_ids = parse_skill_ids(item["kp_id"])
            question_to_skills[qid] = skill_ids
            for skill_id in skill_ids:
                skill_to_questions.setdefault(skill_id, []).append(qid)
                # v1 数据中 kp_desc 是知识点名称，CLI 输出诊断结果时会用到。
                if item.get("kp_desc"):
                    skill_names.setdefault(skill_id, str(item["kp_desc"]))

    qst_num = max(question_to_skills) + 1
    skl_num = max(skill for skills in question_to_skills.values() for skill in skills) + 1

    # forward 只接受一个主知识点。raw 原型对多知识点题目也取第一个知识点。
    question_primary_skill = np.zeros(qst_num, dtype=np.int64)
    for qid, skill_ids in question_to_skills.items():
        question_primary_skill[qid] = skill_ids[0]

    # 学生行为序列统一为 [exercise_id, response, mask]；mask=1 表示有效交互。
    recordings_by_user: Dict[int, List[List[int]]] = {}
    with (data_dir / "student_record.json").open(encoding="utf-8") as file:
        for line in file:
            item = json.loads(line)
            user_id = int(item["student_id"])
            recordings_by_user[user_id] = [
                [int(qid), int(resp), 1]
                for qid, resp in zip(item["question_id"], item["is_corrects"])
            ]

    return ReKTDataBundle(
        qst_num=qst_num,
        usr_num=len(recordings_by_user),
        skl_num=skl_num,
        question_to_skills=question_to_skills,
        question_primary_skill=question_primary_skill,
        skill_to_questions=skill_to_questions,
        skill_names=skill_names,
        recordings_by_user=recordings_by_user,
    )


def format_sequences(sequences: Iterable[List[List[int]]], seq_len: int) -> np.ndarray:
    """将变长学生序列补齐并切分成固定长度训练样本。"""
    formatted = []
    for seq in sequences:
        remainder = len(seq) % seq_len
        pad = 0 if remainder == 0 else seq_len - remainder
        # padding 交互的 mask=0，训练/评估时会被过滤掉。
        padded = seq + [[0, 0, 0]] * pad
        formatted.extend(np.array(padded).reshape(-1, seq_len, 3).tolist())
    return np.array(formatted, dtype=np.int64)
