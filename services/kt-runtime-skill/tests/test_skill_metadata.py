from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SkillMetadataTest(unittest.TestCase):
    def test_skill_description_is_precise_for_routing(self):
        text = (ROOT / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn(
            "description: Use when 用户明确要求对某个学生 ID 做 KT 学情分析、知识点掌握度诊断报告，"
            "或预测该学生的知识点掌握情况；仅提供学生 ID、身份声明或普通学习问答时不要使用。",
            text,
        )


    def test_skill_declares_frontend_policy_markers(self):
        text = (ROOT / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("默认用 `conda run -n kt python scripts/run_kt.py` 执行普通 KT 学情分析。", text)
        self.assertIn("Default student-ID mode requires:", text)
        self.assertIn("- `student_id`: numeric ID such as `40`", text)
        self.assertIn("中文报告读取：`llm_analysis.report_markdown`", text)


if __name__ == "__main__":
    unittest.main()
