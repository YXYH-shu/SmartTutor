from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import torch

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import run_lpp
from lpp_runtime.search.genetic_algorithm import GeneticAlgorithmBase


class CatalogScorer:
    device = torch.device("cpu")
    question_universe_size = 11
    mappings = {1: [1], 2: [2], 3: [3], 4: [4], 5: [5], 6: [6],
                7: [7], 8: [1, 7], 9: [1], 10: [2]}

    def __init__(self):
        self.data = SimpleNamespace(
            skl_num=9,
            skill_to_questions={s: self.questions_of_skill(s) for s in range(1, 8)},
        )
        self.predictions = []
        self.probability = 0.8

    def skills_of(self, question_id):
        return list(self.mappings.get(int(question_id), []))

    def questions_of_skill(self, skill_id):
        return [q for q, skills in self.mappings.items() if int(skill_id) in skills]

    def question_metadata(self, question_id):
        return {"question_desc": f"题目{question_id}", "type": "single_choice"}

    def knowledge_metadata(self, skill_id):
        return {"knowledge_point_id": int(skill_id), "knowledge_point_name": f"知识点{skill_id}"}

    def knowledge_sequence(self, skill_id):
        return {"previous": self.knowledge_metadata(7), "next": self.knowledge_metadata(2)}

    def forward_batch(self, hist_q, hist_a, next_q):
        self.predictions.append((hist_q.tolist(), hist_a.tolist(), next_q.tolist()))
        return torch.tensor([[self.probability]])


@pytest.fixture
def runtime(monkeypatch):
    scorer = CatalogScorer()
    state = SimpleNamespace(scorer=scorer, history=SimpleNamespace(
        question_ids=[7, 1, 8, 7], is_corrects=[0, 1, 0, 1]), ga=None)
    monkeypatch.setattr(run_lpp, "KTScorer", lambda: scorer)
    monkeypatch.setattr(run_lpp, "KTHistoryProvider", lambda _: SimpleNamespace(
        get_history=lambda student_id: state.history))

    class FakeGA:
        def __init__(self, **kwargs):
            state.ga = kwargs

        def run0707(self, **kwargs):
            ace = np.zeros((9, 9))
            weight = np.full((9, 9), 10)
            ace[7, :] = 100  # unrelated empirical effect must not escape the boundary
            ace[2, :] = 0.5
            return {"e_ACEf": ace, "e_weightf": weight,
                    "recommended_questions": [8, 7, 9],
                    "final_score": 0.9, "effect_gain": 0.1}

    monkeypatch.setattr(run_lpp, "GeneticAlgorithmBase", FakeGA)
    return state


def args(**overrides):
    values = dict(student_id="42", topic_skill_ids="5,1,4,2,3", preferred_skill_ids="1,2",
                  seed=None, weights="0.9,0.1", length=3, target_question_id=None,
                  top_k_knowledge=5, min_sample=5, pop_size=4, max_gen=1)
    values.update(overrides)
    return SimpleNamespace(**values)


def test_cli_accepts_optional_ordered_topic_ids():
    assert run_lpp.parse_cli_args(["--student-id", "42"]).topic_skill_ids == ""
    assert run_lpp.parse_cli_args(["--student-id", "42", "--topic-skill-ids", "5,1,4,2,3"]).topic_skill_ids == "5,1,4,2,3"


def test_topic_target_never_scans_unrelated_or_mixed_history(runtime):
    response = run_lpp.run_planning(args())
    assert response["target"]["question_id"] == 1
    assert response["diagnostics"]["scanned_target_count"] == 1
    assert [prediction[2][0][-1] for prediction in runtime.scorer.predictions] == [1]


def test_scope_covers_all_ga_pools_mutation_fallback_and_public_points(runtime, monkeypatch):
    response = run_lpp.run_planning(args())
    allowed_questions = {1, 2, 3, 4, 5, 9, 10}
    for key in ("candidate_pool_all", "candidate_pool_default", "candidate_pool_untried_skill",
                "candidate_pool_wrong_skill", "candidate_pool_target_skill"):
        assert set(runtime.ga[key]) <= allowed_questions, key
    assert runtime.ga["scorer"].questions_of_skill(1) == [1, 9]
    # Exercise real dynamic matrix-guided mutation through the scoped scorer.
    real_ga = GeneticAlgorithmBase(**runtime.ga)
    monkeypatch.setattr(np.random, "choice", lambda values, **_: 7 if isinstance(values, np.ndarray) else values[0])
    mutation_question, _ = real_ga.choice_skills([1])
    assert mutation_question in allowed_questions - {1}
    points = response["recommendation"]["knowledge_points"]
    assert [point["knowledge_point_id"] for point in points] == [5, 1, 4, 2, 3]
    assert len(response["recommendation"]["questions"]) == 5
    assert {q["question_id"] for q in response["recommendation"]["questions"]} <= allowed_questions - {1}
    for item in response["plan_items"]:
        for related in item["related_questions"]:
            assert related["question_id"] in allowed_questions
        for sequence in item["knowledge_sequences"]:
            assert sequence["knowledge_sequence"]["previous"] is None


def test_ace_ranking_filters_before_top_k():
    points, _ = run_lpp.build_top_k_knowledge(
        ace_col=np.array([0, 0, 0.2, 0, 0, 0, 0, 99]),
        weight_col=np.full(8, 10), target_sid=1, top_k=1, min_sample=5,
        allowed_skill_ids={1, 2, 3, 4, 5})
    assert points == [(2, 0.2, 10)]


def test_preferred_topic_skill_order_beats_recency(runtime):
    runtime.history.question_ids = [1, 2, 7]
    runtime.history.is_corrects = [0, 1, 0]
    runtime.scorer.probability = 0.2
    response = run_lpp.run_planning(args(preferred_skill_ids="1,2"))
    assert response["target"]["question_id"] == 1


def test_missing_topic_history_selects_catalog_target_with_real_recent_answers(runtime):
    runtime.history.question_ids = [7, 8, 7, 8]
    runtime.history.is_corrects = [0, 1, 1, 0]
    response = run_lpp.run_planning(args(preferred_skill_ids="2,1"))
    assert response["target"]["question_id"] == 2
    assert response["diagnostics"]["initial_target_source"] == "topic_catalog"
    assert runtime.ga["hist_q"].tolist() == [[8, 7, 8]]
    assert runtime.ga["hist_a"].tolist() == [[1, 1, 0]]
    assert runtime.ga["next_a"].tolist() == [[1, 1, 0]]
    assert runtime.history.question_ids == [7, 8, 7, 8]
    assert runtime.history.is_corrects == [0, 1, 1, 0]


@pytest.mark.parametrize("target", [7, 8])
def test_explicit_unrelated_or_mixed_target_is_rejected(runtime, target):
    with pytest.raises(ValueError, match="主题"):
        run_lpp.run_planning(args(target_question_id=target))
    assert runtime.ga is None


def test_explicit_catalog_target_does_not_require_invented_history(runtime):
    response = run_lpp.run_planning(args(target_question_id=3))
    assert response["target"]["question_id"] == 3
    assert runtime.ga["hist_q"].tolist() == [[1, 8, 7]]
    assert runtime.ga["hist_a"].tolist() == [[1, 0, 1]]


def test_insufficient_topic_points_fails_instead_of_global_fill(runtime):
    with pytest.raises((ValueError, RuntimeError), match="知识点不足"):
        run_lpp.run_planning(args(topic_skill_ids="1,2,3,4"))
    assert runtime.ga is None


def test_insufficient_topic_questions_fails_instead_of_global_fill(runtime):
    runtime.scorer.mappings = {1: [1], 2: [2], 3: [3], 4: [4], 5: [5], 7: [7]}
    with pytest.raises((ValueError, RuntimeError), match="题目不足"):
        run_lpp.run_planning(args())
    assert runtime.ga is None


def test_legacy_without_topic_keeps_original_unrestricted_forward_scan(runtime):
    response = run_lpp.run_planning(args(topic_skill_ids=""))
    assert response["target"]["question_id"] == 7
    assert response["diagnostics"]["scanned_target_count"] == 2
    assert 8 in runtime.ga["candidate_pool_all"]


def test_explicit_topic_history_target_stays_fixed_even_when_mastery_is_high(runtime):
    runtime.history.question_ids = [7, 1, 2, 3]
    runtime.history.is_corrects = [0, 1, 0, 1]
    result = run_lpp.run_planning(args(target_question_id=1))
    assert result['target']['question_id'] == 1
    assert result['diagnostics']['scanned_target_count'] == 1


def test_scoped_public_path_keeps_pedagogical_anchor_and_target_before_ace_fill():
    result = run_lpp.build_knowledge_point_recommendations(
        scorer=CatalogScorer(), top_k_knowledge=[(2, .9, 10), (3, .8, 10), (4, .7, 10), (6, .6, 10), (5, .5, 10)],
        recommended_questions=[], target_skills=[1], fallback_skill_ids=[5, 1, 4, 2, 3, 6],
        topic_skill_ids=[5, 1, 4, 2, 3, 6],
    )
    ids = [x['knowledge_point_id'] for x in result]
    assert 5 in ids and 1 in ids
    assert ids[0] == 5


def test_preferred_core_without_history_uses_its_catalog_target_instead_of_other_topic_history(runtime):
    runtime.history.question_ids = [1, 2, 7]
    runtime.history.is_corrects = [0, 1, 0]
    response = run_lpp.run_planning(args(topic_skill_ids='1,2,3,4,5,6', preferred_skill_ids='6'))
    assert response['target']['question_id'] == 6
    assert 6 in [p['knowledge_point_id'] for p in response['recommendation']['knowledge_points']]


def test_preferred_core_target_does_not_drift_to_noncore_history_when_mastery_high(runtime):
    runtime.history.question_ids = [1, 2, 7]
    runtime.history.is_corrects = [1, 0, 0]
    response = run_lpp.run_planning(args(preferred_skill_ids='1'))
    assert response['target']['question_id'] == 1


def test_public_path_preserves_all_five_current_core_goals_before_optional_safety_anchor():
    result = run_lpp.build_knowledge_point_recommendations(
        scorer=CatalogScorer(), top_k_knowledge=[(5, .9, 10), (7, .8, 10)],
        recommended_questions=[], target_skills=[1], fallback_skill_ids=[5, 1, 2, 3, 4, 6, 7],
        topic_skill_ids=[5, 1, 2, 3, 4, 6, 7], core_skill_ids=[1, 2, 3, 4, 6],
    )
    assert [point['knowledge_point_id'] for point in result] == [1, 2, 3, 4, 6]
