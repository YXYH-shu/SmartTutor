import os
import sys
import unittest
from unittest.mock import patch


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)


from kt_runtime.config import DEFAULT_CONFIG  # noqa: E402
from kt_runtime.contracts import KTPredictRequest  # noqa: E402
from kt_runtime.request_factory import build_request_from_trace  # noqa: E402


class SchemaSimplificationTest(unittest.TestCase):
    def test_contract_accepts_current_request_shape(self):
        request = KTPredictRequest.from_dict(
            {
                "request_id": "schema-demo",
                "student_trace": [{"skill_id": 52, "correct": 1}],
                "targets": [{"skill_id": 51}],
                "analysis_context": {"history_context": "最近在学电路。"},
            }
        )

        self.assertEqual(request.request_id, "schema-demo")
        self.assertEqual(request.task, "predict_correctness")
        self.assertEqual(request.student_trace[0].skill_id, 52)
        self.assertEqual(request.targets[0].skill_id, 51)
        self.assertEqual(request.analysis_context["history_context"], "最近在学电路。")

    def test_contract_uses_only_current_top_level_fields(self):
        request = KTPredictRequest.from_dict(
            {
                "request_id": "current-demo",
                "task": "predict_correctness",
                "student_trace": [{"skill_id": 52, "correct": 1}],
                "targets": [{"skill_id": 51}],
                "device": "cuda:0",
                "analysis_context": {"history_context": "当前字段上下文。"},
            }
        )

        self.assertEqual(request.request_id, "current-demo")
        self.assertEqual(request.targets[0].skill_id, 51)
        self.assertEqual(request.device, "cuda:0")
        self.assertEqual(request.analysis_context["history_context"], "当前字段上下文。")

    def test_request_factory_outputs_simplified_schema_and_keeps_targets(self):
        with patch("kt_runtime.request_factory.infer_num_skills", return_value=3), patch(
            "kt_runtime.request_factory.load_kp_catalog_from_config", return_value={2: {}, 3: {}}
        ):
            payload = build_request_from_trace(
                [{"skill_id": 1, "correct": 1}],
                raw_targets="2,3",
                request_id="factory-demo",
                history_context="上下文。",
            )

        self.assertEqual(
            set(payload),
            {
                "request_id",
                "task",
                "student_trace",
                "targets",
                "rekt_skill_arg",
                "device",
                "analysis_enabled",
                "analysis_context",
            },
        )
        self.assertEqual(payload["targets"], [{"skill_id": 2}, {"skill_id": 3}])
        self.assertEqual(payload["rekt_skill_arg"], "2,3")
        self.assertEqual(payload["device"], "cuda:0")
        self.assertEqual(payload["analysis_context"]["history_context"], "上下文。")

    def test_request_factory_omits_unpredictable_targets_from_all(self):
        with patch("kt_runtime.request_factory.infer_num_skills", return_value=3), patch(
            "kt_runtime.request_factory.load_kp_catalog_from_config", return_value={1: {}, 2: {}}
        ):
            payload = build_request_from_trace(
                [{"skill_id": 1, "correct": 1}],
                raw_targets="all",
                request_id="factory-demo",
            )

        self.assertEqual(payload["targets"], [{"skill_id": 1}, {"skill_id": 2}])
        self.assertEqual(payload["rekt_skill_arg"], "all")

    def test_request_factory_rejects_unpredictable_explicit_target(self):
        with patch("kt_runtime.request_factory.infer_num_skills", return_value=3), patch(
            "kt_runtime.request_factory.load_kp_catalog_from_config", return_value={1: {}, 2: {}}
        ):
            with self.assertRaisesRegex(ValueError, "no REKT question mapping"):
                build_request_from_trace(
                    [{"skill_id": 1, "correct": 1}],
                    raw_targets="3",
                    request_id="factory-demo",
                )

    def test_default_runtime_device_is_gpu_first(self):
        self.assertEqual(DEFAULT_CONFIG["runtime"]["device"], "cuda:0")


if __name__ == "__main__":
    unittest.main()
