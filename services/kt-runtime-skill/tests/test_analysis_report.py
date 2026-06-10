import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)


from kt_runtime.analysis_report import (  # noqa: E402
    _build_knowledge_points,
    _build_learning_analysis,
    _build_mastery_rows,
    _learning_analysis_style_template,
    _render_report_markdown,
    _selected_knowledge_points,
)


class AnalysisReportTest(unittest.TestCase):
    def test_learning_analysis_is_agent_rewrite_task(self):
        selected = [
            {
                "skill_id": 51,
                "report_skill_id": "KP051",
                "knowledge_point_name": "电路基本元件",
                "knowledge_point_description": "知道电路由电源、导线、开关和用电器组成。",
                "topic_name": "电路",
            }
        ]
        mastery_rows = [
            {
                "skill_id": "KP051",
                "source_skill_id": 51,
                "knowledge_point_name": "电路基本元件",
                "predicted_mastery": "28.77%",
                "mastery_status": "生疏",
                "evidence": "-",
            }
        ]

        analysis = _build_learning_analysis(
            selected,
            mastery_rows,
            [],
            {
                "history_context": "我最近在学电路。",
                "initial_query": "",
                "sequence_summary": {"history_length": 200},
            },
        )

        self.assertEqual(analysis["mode"], "agent_rewrite_required")
        self.assertIn("电路", analysis["context_anchor"])
        self.assertEqual(analysis["average_mastery_percent"], 29)
        self.assertIn("总体学情概述", analysis["style_template"])
        self.assertTrue(any("Markdown 模板" in item for item in analysis["writing_requirements"]))
        self.assertFalse(any("整体学情画像" in item for item in analysis["writing_requirements"]))
        self.assertEqual(
            analysis["source_materials"]["weak_points"][0]["knowledge_point_name"],
            "电路基本元件",
        )

    def test_mastery_status_uses_rekt_cli_field(self):
        mastery_rows = _build_mastery_rows(
            [
                {
                    "report_skill_id": "KP099",
                    "skill_id": 99,
                    "knowledge_point_name": "高分知识点",
                    "probability_correct": 0.99,
                    "history_count": 1,
                    "recent_count": 1,
                    "mastery_status": "精通",
                },
                {
                    "report_skill_id": "KP085",
                    "skill_id": 85,
                    "knowledge_point_name": "熟练知识点",
                    "probability_correct": 0.85,
                    "history_count": 1,
                    "recent_count": 1,
                    "mastery_status": "掌握",
                },
            ],
            risk_flags=[],
        )

        self.assertEqual(mastery_rows[0]["mastery_status"], "精通")
        self.assertEqual(mastery_rows[1]["mastery_status"], "掌握")

    def test_mastery_table_omits_priority_and_uses_empty_evidence_marker(self):
        mastery_rows = _build_mastery_rows(
            [
                {
                    "report_skill_id": "KP001",
                    "skill_id": 1,
                    "knowledge_point_name": "目录知识点名称",
                    "probability_correct": 0.625,
                    "history_count": 3,
                    "recent_count": 1,
                    "mastery_status": "掌握",
                    "selection_bucket": "mid_mastery",
                }
            ],
            risk_flags=["risk"],
        )

        self.assertEqual(mastery_rows[0]["evidence"], "-")
        self.assertEqual(mastery_rows[0]["selection_bucket"], "mid_mastery")
        self.assertNotIn("priority", mastery_rows[0])

        markdown = _render_report_markdown(
            theme_judgement={"text": "主题。"},
            knowledge_points=[],
            learning_analysis={
                "mode": "agent_rewrite_required",
                "context_anchor": "当前学习上下文",
                "average_mastery_percent": 63,
                "risk_flags": [],
                "source_materials": {"history_summary": {}},
            },
            mastery_rows=mastery_rows,
            analysis_process={"history_summary": {}},
            selected_knowledge_points=[],
        )

        self.assertIn("| 知识点ID | 知识点名称 | 预测掌握度 | 掌握状态 | 判断依据 |", markdown)
        self.assertIn("| KP001 | 目录知识点名称 | 62.5% | 掌握 | - |", markdown)
        self.assertNotIn("优先级", markdown)

    def test_mastery_percent_preserves_rekt_cli_decimal(self):
        mastery_rows = _build_mastery_rows(
            [
                {
                    "report_skill_id": "KP216",
                    "skill_id": 216,
                    "knowledge_point_name": "昆虫两栖鸟发育",
                    "probability_correct": 0.0003,
                    "mastery_percent": 0.03,
                    "mastery_status": "生疏",
                }
            ],
            risk_flags=[],
        )

        self.assertEqual(mastery_rows[0]["predicted_mastery"], "0.03%")

    def test_knowledge_points_table_omits_source_basis(self):
        knowledge_points = _build_knowledge_points(
            [
                {
                    "report_skill_id": "KP051",
                    "skill_id": 51,
                    "knowledge_point_name": "电路基本元件",
                    "type": "概念",
                    "selection_bucket": "ngram",
                }
            ],
            context={"history_context": "电路"},
        )

        self.assertNotIn("source_basis", knowledge_points[0])

        markdown = _render_report_markdown(
            theme_judgement={"text": "主题。"},
            knowledge_points=knowledge_points,
            learning_analysis={
                "mode": "agent_rewrite_required",
                "context_anchor": "电路",
                "average_mastery_percent": 0,
                "risk_flags": [],
                "source_materials": {"history_summary": {}},
            },
            mastery_rows=[],
            analysis_process={"history_summary": {}},
            selected_knowledge_points=[],
        )

        self.assertIn("| 知识点ID | 知识点名称 | 类型 |", markdown)
        self.assertIn("| KP051 | 电路基本元件 | 概念 |", markdown)
        self.assertNotIn("来源依据", markdown)

    def test_selected_knowledge_points_output_keeps_only_report_details(self):
        rows = _selected_knowledge_points(
            [
                {
                    "report_skill_id": "KP051",
                    "skill_id": 51,
                    "knowledge_point_name": "电路基本元件",
                    "knowledge_point_description": "知道电路由电源、导线、开关和用电器组成。",
                    "type": "概念",
                    "topic_name": "电路",
                    "selection_score": 0.99,
                    "matched_terms": ["电路"],
                    "domain_name": "小学科学",
                }
            ]
        )

        self.assertEqual(
            rows,
            [
                {
                    "knowledge_point_id": "KP051",
                    "source_skill_id": 51,
                    "knowledge_point_name": "电路基本元件",
                    "knowledge_point_description": "知道电路由电源、导线、开关和用电器组成。",
                    "type": "概念",
                    "topic_name": "电路",
                }
            ],
        )

        markdown = _render_report_markdown(
            theme_judgement={"text": "主题。"},
            knowledge_points=[],
            learning_analysis={
                "mode": "agent_rewrite_required",
                "context_anchor": "电路",
                "average_mastery_percent": 0,
                "risk_flags": [],
                "source_materials": {"history_summary": {}},
            },
            mastery_rows=[],
            analysis_process={"history_summary": {}},
            selected_knowledge_points=rows,
        )

        self.assertIn("## 4. 诊断知识点明细", markdown)
        self.assertNotIn("## 4. 选中知识点明细", markdown)
        self.assertIn("knowledge_point_description", markdown)
        self.assertNotIn("KT 原始输出", markdown)
        self.assertNotIn("## 5. KT 原始预测数据", markdown)
        self.assertNotIn("selection_score", markdown)
        self.assertNotIn("matched_terms", markdown)

    def test_report_markdown_contains_agent_rewrite_marker(self):
        markdown = _render_report_markdown(
            theme_judgement={"text": "主题。"},
            knowledge_points=[],
            learning_analysis={
                "mode": "agent_rewrite_required",
                "context_anchor": "我在学电路。",
                "average_mastery_percent": 37,
                "risk_flags": [],
                "source_materials": {
                    "history_summary": {
                        "history_length": 200,
                        "accuracy": 0.51,
                        "recent_window": 20,
                        "recent_accuracy": 0.55,
                    },
                    "weak_points": [
                        {
                            "knowledge_point_name": "电路基本元件",
                            "predicted_mastery": "28.77%",
                        }
                    ],
                },
            },
            mastery_rows=[],
            analysis_process={"history_summary": {}},
            selected_knowledge_points=[],
        )

        self.assertIn("AGENT_REWRITE_REQUIRED_BEGIN", markdown)
        self.assertIn("电路基本元件（28.77%）", markdown)
        self.assertIn("style_template", markdown)
        self.assertIn("自然语言分析模板", markdown)
        self.assertNotIn("# 学情分析报告", markdown)
        self.assertIn("### 3.1 总体学情概述", markdown)
        self.assertIn("### 3.2 优势知识点分析", markdown)
        self.assertIn("### 3.3 薄弱模块诊断", markdown)
        self.assertIn("### 3.4 教学建议", markdown)
        self.assertIn("不要输出开场说明、分隔线或结尾说明", markdown)
        self.assertIn("第一行必须是：`### 3.1 总体学情概述`", markdown)
        self.assertIn("在 `### 3.1 总体学情概述` 之前不要输出任何文字", markdown)
        self.assertIn("模板仅供参考，不要直接输出模板原文", markdown)
        self.assertNotIn("请按以下小标题写作", markdown)
        self.assertNotIn("整体学情画像", markdown)
        self.assertNotIn("风险专项分析", markdown)

    def test_learning_analysis_style_template_uses_standard_asset(self):
        template = _learning_analysis_style_template()

        self.assertNotIn("# 学情分析报告", template)
        self.assertIn("### 3.1 总体学情概述", template)
        self.assertIn("### 3.3 薄弱模块诊断", template)

    def test_report_markdown_omits_raw_kt_prediction_json_section(self):
        mastery_rows = [
            {
                "skill_id": "KP051",
                "source_skill_id": 51,
                "knowledge_point_name": "电路基本元件",
                "predicted_mastery": "28.77%",
                "mastery_status": "薄弱",
                "evidence": "-",
            }
        ]

        markdown = _render_report_markdown(
            theme_judgement={"text": "主题。"},
            knowledge_points=[],
            learning_analysis={
                "mode": "agent_rewrite_required",
                "context_anchor": "电路",
                "average_mastery_percent": 29,
                "risk_flags": [],
                "source_materials": {"history_summary": {}},
            },
            mastery_rows=mastery_rows,
            analysis_process={"history_summary": {}},
            selected_knowledge_points=[],
        )

        self.assertNotIn("## 5. KT 原始预测数据", markdown)
        self.assertNotIn('"predicted_mastery": "28.77%"', markdown)
        self.assertNotIn('"mastery_status": "薄弱"', markdown)


if __name__ == "__main__":
    unittest.main()
