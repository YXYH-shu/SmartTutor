import argparse
import json
import os
import sys


if __package__ in (None, ""):
    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

from kt_runtime.config import DEFAULT_CONFIG_PATH
from kt_runtime.contracts import KTPredictResponse
from kt_runtime.kt_cli_runtime import predict_via_kt_cli
from kt_runtime.request_factory import (
    build_request_from_student_id,
    build_request_from_trace,
    parse_trace_json,
    parse_trace_pairs,
)


def parse_args():
    parser = argparse.ArgumentParser(description="KT 运行时统一入口。")
    parser.add_argument(
        "--config-file",
        default=DEFAULT_CONFIG_PATH,
        help="TOML 配置文件路径，默认使用 skill 内置配置。",
    )

    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--request-file", help="完整 KT 请求 JSON 文件路径。")
    source_group.add_argument("--request-json", help="完整 KT 请求 JSON 字符串。")
    source_group.add_argument("--student-id", help="学生 ID。脚本会通过本地 KT 数据集读取该学生的历史作答序列。")
    source_group.add_argument(
        "--trace-pairs",
        help="手工输入历史序列，格式如 27:1,13:0,8:1。当前 skill_id 表示 kp_id，不再是 topic_id。",
    )
    source_group.add_argument(
        "--trace-json",
        help='手工输入 student_trace JSON，例如 [{"skill_id":27,"correct":1}]。当前 skill_id 表示 kp_id。',
    )
    source_group.add_argument(
        "--trace-file",
        help="student_trace JSON 文件路径，文件内容应是一个列表。",
    )

    parser.add_argument(
        "--targets",
        help="预测目标 kp_id，格式如 15,16,17；不传时使用配置文件中的默认值。",
    )
    parser.add_argument(
        "--history-limit",
        type=int,
        default=None,
        help="仅在 --student-id 模式下生效，用来覆盖配置文件中的历史截断长度。",
    )
    parser.add_argument("--request-id", help="自定义 request_id。")
    parser.add_argument("--device", help="覆盖配置文件中的运行设备。")
    parser.add_argument("--initial-query", help="传给分析报告的当前问题描述。")
    parser.add_argument("--history-context", help="传给分析报告的额外历史上下文。")
    parser.add_argument(
        "--disable-analysis-report",
        action="store_true",
        help="关闭学情分析报告，只保留预测结果。",
    )
    return parser.parse_args()


def load_payload(args):
    if args.request_file:
        with open(args.request_file, "r", encoding="utf-8") as file_obj:
            return json.load(file_obj)
    if args.request_json:
        return json.loads(args.request_json)
    if args.student_id:
        payload = build_request_from_student_id(
            student_id=args.student_id,
            raw_targets=args.targets,
            config_path=args.config_file,
            request_id=args.request_id,
            device=args.device,
            history_limit=args.history_limit,
            initial_query=args.initial_query,
            history_context=args.history_context,
        )
        payload["student_id"] = str(args.student_id)
        if args.history_limit is not None:
            payload["history_limit"] = int(args.history_limit)
    else:
        if args.trace_pairs:
            student_trace = parse_trace_pairs(args.trace_pairs)
        elif args.trace_json:
            student_trace = parse_trace_json(args.trace_json)
        else:
            with open(args.trace_file, "r", encoding="utf-8") as file_obj:
                student_trace = parse_trace_json(file_obj.read())

        payload = build_request_from_trace(
            student_trace=student_trace,
            raw_targets=args.targets,
            config_path=args.config_file,
            request_id=args.request_id,
            device=args.device,
            initial_query=args.initial_query,
            history_context=args.history_context,
        )

    if args.disable_analysis_report:
        payload["analysis_enabled"] = False
    return payload


def build_error_response(request_id: str, task: str, message: str) -> KTPredictResponse:
    return KTPredictResponse(
        request_id=request_id,
        status="error",
        task=task,
        message=message,
        predictions=[],
        metrics={},
        model_info={},
        errors=[message],
    )


def main():
    args = parse_args()
    try:
        payload = load_payload(args)
        response = predict_via_kt_cli(payload)
    except Exception as exc:
        request_id = "unknown-request"
        task = "unknown-task"
        if isinstance(locals().get("payload"), dict):
            request_id = str(payload.get("request_id", request_id))
            task = str(payload.get("task", task))
        response = build_error_response(request_id, task, str(exc))

    print(json.dumps(response.to_dict(), ensure_ascii=False, indent=2))
    if response.status != "ok":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
