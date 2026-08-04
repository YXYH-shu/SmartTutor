from __future__ import annotations

import sys
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from run_lpp import choose_starting_target_index  # noqa: E402
from lpp_runtime.scorers.rekt_scorer import default_kt_runtime_skill_root  # noqa: E402


def test_default_kt_runtime_path_uses_smarttutor_sibling_service():
    expected = Path(__file__).resolve().parents[2] / "kt-runtime-skill"
    assert default_kt_runtime_skill_root() == expected


def _skills_for_question(question_id: int) -> list[int]:
    return {
        10: [2],
        11: [1],
        12: [2],
        13: [1],
        14: [3],
    }.get(question_id, [])


def test_explicit_question_takes_precedence_over_preferred_skills():
    index, source = choose_starting_target_index(
        question_ids=[10, 11, 12, 13, 14],
        target_question_id=11,
        preferred_skill_ids=[2, 1],
        skills_for_question=_skills_for_question,
        length=3,
    )

    assert index == 1
    assert source == "explicit_question"


def test_weakest_matching_skill_uses_its_most_recent_history_question():
    index, source = choose_starting_target_index(
        question_ids=[10, 11, 12, 13, 14],
        target_question_id=None,
        preferred_skill_ids=[2, 1],
        skills_for_question=_skills_for_question,
        length=3,
    )

    assert index == 2
    assert source == "kt_weak_skill"


def test_missing_preferred_skills_falls_back_to_original_default():
    index, source = choose_starting_target_index(
        question_ids=[10, 11, 12, 13, 14],
        target_question_id=None,
        preferred_skill_ids=[99],
        skills_for_question=_skills_for_question,
        length=3,
    )

    assert index == 3
    assert source == "default_history_window"
