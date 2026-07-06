import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)


from kt_runtime.ngram_selector import select_relevant_knowledge_points  # noqa: E402


def _candidate(
    skill_id,
    *,
    name,
    probability,
    history_count=0,
    recent_count=0,
    description="电路相关知识点",
    topic_name="电路",
):
    return {
        "skill_id": skill_id,
        "knowledge_point_name": name,
        "knowledge_point_description": description,
        "topic_name": topic_name,
        "domain_name": "科学",
        "skill_names": [],
        "probability_correct": probability,
        "history_count": history_count,
        "recent_count": recent_count,
    }


class NgramSelectorTest(unittest.TestCase):
    def test_selects_top_18_by_context_description_ngram_only(self):
        candidates = [
            _candidate(
                skill_id,
                name=f"电路知识{skill_id}",
                description="闭合回路 电流 导体 绝缘体 电路",
                probability=0.0 if skill_id % 2 else 0.99,
                history_count=30,
                recent_count=5,
                topic_name="ignored topic",
            )
            for skill_id in range(1, 19)
        ]
        candidates.extend(
            _candidate(
                skill_id,
                name=f"动物发育知识{skill_id}",
                description="动物 生命周期 胎生 卵生 发育",
                probability=0.50,
                history_count=100,
                recent_count=20,
                topic_name="电路",
            )
            for skill_id in range(101, 121)
        )

        selected = select_relevant_knowledge_points(
            candidates,
            initial_query="",
            history_context="我最近在学闭合回路、电流、电路、导体和绝缘体。",
            recent_interactions=[
                {"knowledge_point_name": "动物生命周期", "topic_name": "动物生长发育"}
            ],
            top_k=18,
        )

        selected_ids = [item["skill_id"] for item in selected]
        self.assertEqual(set(selected_ids), set(range(1, 19)))
        self.assertTrue(all(item["selection_bucket"] == "ngram" for item in selected))

    def test_name_and_topic_do_not_drive_selection(self):
        candidates = [
            _candidate(
                1,
                name="电路名称但描述无关",
                description="动物 生命周期 胎生 卵生 发育",
                topic_name="电路",
                probability=0.99,
                history_count=100,
                recent_count=20,
            ),
            _candidate(
                2,
                name="普通名称",
                description="闭合回路 电流 导体 绝缘体 电路",
                topic_name="动物发育",
                probability=0.0,
                history_count=0,
                recent_count=0,
            ),
        ]

        selected = select_relevant_knowledge_points(
            candidates,
            initial_query="",
            history_context="闭合回路和电流",
            recent_interactions=[],
            top_k=1,
        )

        self.assertEqual(selected[0]["skill_id"], 2)

    def test_ignores_mid_mastery_bias_when_ranking(self):
        candidates = []
        for skill_id in range(1, 19):
            candidates.append(
                _candidate(
                    skill_id,
                    name=f"高分相关知识{skill_id}",
                    description="闭合回路 电流 导体 绝缘体 电路",
                    probability=0.99,
                )
            )
        for skill_id in range(19, 25):
            candidates.append(
                _candidate(
                    skill_id,
                    name=f"中等掌握无关知识{skill_id}",
                    description="动物 生命周期 胎生 卵生 发育",
                    probability=0.50,
                )
            )

        selected = select_relevant_knowledge_points(
            candidates,
            initial_query="",
            history_context="闭合回路和电流",
            recent_interactions=[],
            top_k=18,
        )

        selected_ids = [item["skill_id"] for item in selected]
        self.assertEqual(set(selected_ids), set(range(1, 19)))

    def test_context_matches_outrank_high_frequency_history_when_context_is_available(self):
        candidates = []
        for skill_id in range(1, 19):
            candidates.append(
                _candidate(
                    skill_id,
                    name=f"电路知识{skill_id}",
                    description="闭合回路 电流 导体 绝缘体 电路",
                    topic_name="电磁相互作用",
                    probability=0.45,
                    history_count=0,
                    recent_count=0,
                )
            )
        for skill_id in range(101, 121):
            candidates.append(
                _candidate(
                    skill_id,
                    name=f"动物发育知识{skill_id}",
                    description="动物 生命周期 胎生 卵生 发育",
                    topic_name="动物生长发育",
                    probability=0.50,
                    history_count=30,
                    recent_count=5,
                )
            )

        selected = select_relevant_knowledge_points(
            candidates,
            initial_query="",
            history_context="我最近在学闭合回路、电流、电路、导体和绝缘体。",
            recent_interactions=[],
            top_k=18,
        )

        selected_ids = [item["skill_id"] for item in selected]
        self.assertTrue(all(1 <= skill_id <= 18 for skill_id in selected_ids))
        self.assertTrue(all(skill_id < 100 for skill_id in selected_ids))

    def test_recent_interactions_are_used_only_when_context_is_empty(self):
        candidates = [
            _candidate(
                1,
                name="电路基本元件",
                description="闭合回路 电流 导体 绝缘体 电路",
                probability=0.1,
            ),
            _candidate(
                2,
                name="动物生命周期",
                description="动物 生命周期 胎生 卵生 昆虫两栖鸟发育",
                probability=0.1,
            ),
        ]

        selected = select_relevant_knowledge_points(
            candidates,
            initial_query="",
            history_context="",
            recent_interactions=[
                {
                    "knowledge_point_name": "动物生命周期",
                    "knowledge_point_description": "动物 生命周期 胎生 卵生 昆虫两栖鸟发育",
                }
            ],
            top_k=1,
        )

        self.assertEqual(selected[0]["skill_id"], 2)

    def test_force_context_does_not_match_sound_light_from_generic_terms(self):
        candidates = []
        for skill_id in range(60, 78):
            candidates.append(
                _candidate(
                    skill_id,
                    name=f"力学知识{skill_id}",
                    description="重力 摩擦力 弹力 牛顿 受力分析 力改变运动状态",
                    topic_name="力是改变物体运动状态的原因",
                    probability=0.85,
                    history_count=0,
                    recent_count=0,
                )
            )
        candidates.extend(
            [
                _candidate(
                    91,
                    name="凸透镜成像",
                    description="保护视力和用眼卫生",
                    topic_name="声音与光的传播",
                    probability=0.5,
                    history_count=50,
                    recent_count=10,
                ),
                _candidate(
                    240,
                    name="月相变化规律",
                    description="月相变化规律",
                    topic_name="地月系统",
                    probability=0.5,
                    history_count=50,
                    recent_count=10,
                ),
                _candidate(
                    122,
                    name="常见动物特征",
                    description="动物运动和生命周期",
                    topic_name="动物生长发育",
                    probability=0.5,
                    history_count=50,
                    recent_count=10,
                ),
            ]
        )

        selected = select_relevant_knowledge_points(
            candidates,
            initial_query="",
            history_context="我刚刚聊的是力和运动，请帮我分析力学相关知识。",
            recent_interactions=[],
            top_k=18,
        )

        selected_ids = [item["skill_id"] for item in selected]
        self.assertEqual(set(selected_ids), set(range(60, 78)))


if __name__ == "__main__":
    unittest.main()
