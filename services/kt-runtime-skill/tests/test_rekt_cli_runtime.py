import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)


from kt_runtime.contracts import KTPredictRequest  # noqa: E402
from kt_runtime.config import SKILL_ROOT, load_runtime_config  # noqa: E402
from kt_runtime.rekt_cli_runtime import (  # noqa: E402
    _rekt_checkpoint,
    _rekt_cli_path,
    _rekt_data_dir,
    _skill_relative_path,
    _missing_prediction_targets,
    _predictions_from_rekt_rows,
    parse_rekt_json_lines,
)


class ReKTCLIRuntimeTest(unittest.TestCase):
    def test_default_rekt_paths_are_inside_skill_directory(self):
        config = load_runtime_config()

        for path in (
            _rekt_cli_path(config),
            _rekt_data_dir(config),
            _rekt_checkpoint(config),
        ):
            self.assertTrue(
                os.path.abspath(path).startswith(os.path.abspath(SKILL_ROOT)),
                path,
            )
            self.assertNotIn("/home/duanzt/skills/rekt", os.path.abspath(path))

    def test_relative_rekt_paths_resolve_from_skill_root(self):
        self.assertEqual(
            _skill_relative_path("assets/rekt/dataset"),
            os.path.join(SKILL_ROOT, "assets", "rekt", "dataset"),
        )

    def test_default_rekt_config_allows_cpu_fallback(self):
        config = load_runtime_config()

        self.assertIs(config["rekt"]["allow_cpu_fallback"], True)

    def test_parse_rekt_json_lines_keeps_mastery_rows(self):
        rows = parse_rekt_json_lines(
            '\n'.join(
                [
                    '{"学生id": 5}',
                    '{"知识点": "力", "掌握度": 72.5, "掌握情况": "掌握", "知识点id": 3}',
                    'warning text',
                ]
            )
        )

        self.assertEqual(rows, [{"知识点": "力", "掌握度": 72.5, "掌握情况": "掌握", "知识点id": 3}])

    def test_predictions_use_rekt_mastery_status(self):
        request = KTPredictRequest.from_dict(
            {
                "request_id": "demo",
                "student_trace": [{"skill_id": 1, "correct": 1}],
                "targets": [{"skill_id": 3}],
            }
        )

        predictions = _predictions_from_rekt_rows(
            request,
            [{"知识点": "力", "掌握度": 72.5, "掌握情况": "掌握", "知识点id": 3}],
        )

        self.assertEqual(predictions[0].probability_correct, 0.725)
        self.assertEqual(predictions[0].extras["mastery_status"], "掌握")
        self.assertEqual(predictions[0].extras["mastery_percent"], 72.5)

    def test_predictions_do_not_fill_missing_rekt_rows_with_zero(self):
        request = KTPredictRequest.from_dict(
            {
                "request_id": "demo",
                "student_trace": [{"skill_id": 1, "correct": 1}],
                "targets": [{"skill_id": 3}, {"skill_id": 4}],
            }
        )

        rows = [{"知识点": "力", "掌握度": 72.5, "掌握情况": "掌握", "知识点id": 3}]
        predictions = _predictions_from_rekt_rows(request, rows)

        self.assertEqual([item.target["skill_id"] for item in predictions], [3])
        self.assertEqual(_missing_prediction_targets(request, rows), [4])


if __name__ == "__main__":
    unittest.main()
