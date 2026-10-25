import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)


from kt_runtime.student_source import (  # noqa: E402
    fetch_student_history,
    infer_num_skills,
    load_kp_catalog_from_config,
)


def _write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as file_obj:
        for row in rows:
            file_obj.write(json.dumps(row, ensure_ascii=False) + "\n")


def _config(data_dir):
    return {
        "runtime": {"backend": "kt_json", "device": "cpu"},
        "kt": {"data_dir": data_dir, "checkpoint_path": "/tmp/kt.pt"},
        "model": {},
        "history": {"max_interactions": 2, "selection": "recent"},
        "analysis": {"recent_window": 2},
        "prediction": {"default_targets": "all"},
    }


class KTJsonBackendTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.data_dir = self.tmpdir.name
        _write_jsonl(
            os.path.join(self.data_dir, "exercise_info.json"),
            [
                {
                    "question_id": "10",
                    "kp_id": "1",
                    "kp_desc": "物体外部特征分类",
                    "topic_id": "7",
                    "topic_desc": "物质特性",
                    "grade": "1~2年级",
                },
                {
                    "question_id": "11",
                    "kp_id": "2",
                    "kp_desc": "常见材料识别",
                    "topic_id": "7",
                    "topic_desc": "物质特性",
                    "grade": "1~2年级",
                },
            ],
        )
        _write_jsonl(
            os.path.join(self.data_dir, "student_record.json"),
            [
                {
                    "student_id": "1",
                    "question_id": ["10", "11", "10"],
                    "is_corrects": ["1", "0", "1"],
                }
            ],
        )
        with open(os.path.join(self.data_dir, "knowledges.json"), "w", encoding="utf-8") as file_obj:
            json.dump(
                [
                    {
                        "id": 1,
                        "name": "目录知识点名称",
                        "description": "目录中的知识点描述。",
                        "topic_id": 7,
                        "domain_id": 3,
                    },
                    {
                        "id": 3,
                        "name": "无题目映射知识点",
                        "description": "目录中存在但没有题目映射。",
                    }
                ],
                file_obj,
                ensure_ascii=False,
            )

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_fetch_student_history_reads_kt_json_without_network_api(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("API should not be called")):
            bundle = fetch_student_history(_config(self.data_dir), "1")

        self.assertEqual(bundle["student_id"], "1")
        self.assertEqual(bundle["student_name"], "KTStudent000001")
        self.assertEqual(
            bundle["student_trace"],
            [
                {"skill_id": 2, "correct": 0, "step": 2, "item_id": 11},
                {"skill_id": 1, "correct": 1, "step": 3, "item_id": 10},
            ],
        )
        self.assertEqual(bundle["recent_interactions"][0]["question_id"], 11)
        self.assertEqual(bundle["summary"]["history_length"], 2)
        self.assertEqual(bundle["summary"]["correct_count"], 1)

    def test_fetch_student_history_caps_kt_history_to_max_seq_len(self):
        config = _config(self.data_dir)
        config["history"] = {"max_interactions": 300, "selection": "recent"}
        config["kt"]["max_seq_len"] = 2

        bundle = fetch_student_history(config, "1")

        self.assertEqual(
            bundle["student_trace"],
            [
                {"skill_id": 2, "correct": 0, "step": 2, "item_id": 11},
                {"skill_id": 1, "correct": 1, "step": 3, "item_id": 10},
            ],
        )

    def test_load_kp_catalog_reads_kt_exercise_info(self):
        catalog = load_kp_catalog_from_config(_config(self.data_dir))

        self.assertEqual(sorted(catalog), [1, 2])
        self.assertNotIn(3, catalog)
        self.assertEqual(catalog[1]["knowledge_point_name"], "目录知识点名称")
        self.assertEqual(catalog[1]["knowledge_point_description"], "目录中的知识点描述。")
        self.assertEqual(catalog[1]["topic_id"], 7)
        self.assertEqual(catalog[1]["topic_name"], "物质特性")
        self.assertEqual(catalog[1]["domain_id"], 3)
        self.assertEqual(catalog[1]["question_count"], 1)
        self.assertEqual(catalog[1]["hit_count"], 2)

    def test_infer_num_skills_uses_kt_json_max_kp_id(self):
        self.assertEqual(infer_num_skills(_config(self.data_dir)), 3)


if __name__ == "__main__":
    unittest.main()
