"""REKT 诊断命令行入口。"""

import argparse
import json

try:
    from .config import ReKTConfig
    from .service import ReKTDiagnoser
except ImportError:
    from config import ReKTConfig
    from service import ReKTDiagnoser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="运行 REKT 学生知识追踪诊断")
    parser.add_argument("--user_id", default=288, help="Student id in recordings.jsonl")
    parser.add_argument("--data_dir", default=None, help="Directory containing ReKT jsonl data")
    parser.add_argument("--checkpoint", default=None, help="Path to ReKT checkpoint")
    parser.add_argument("--device", default=None, help="Torch device, e.g. cuda:0 or cpu")
    parser.add_argument("--history_limit", type=int, default=None, help="Number of recent interactions to use")
    parser.add_argument("--skill_id", default="local", help="Skill scope: all, local, one id, or comma-separated ids")
    return parser


def mastery_level(score: float) -> str:
    """将 0-1 掌握度分数映射为四档中文描述。"""
    if score < 0.25:
        return "生疏"
    if score < 0.5:
        return "薄弱"
    if score < 0.75:
        return "掌握"
    return "精通"


def print_diagnosis(result, skill_names: dict[int, str]) -> None:
    """按工具调用约定输出 JSON Lines 文本诊断结果。"""
    print(json.dumps({"学生id": result.user_id}, ensure_ascii=False))
    for item in result.skills:
        score = float(item.knowledge_state)
        row = {
            "知识点": skill_names.get(item.skill_id, f"知识点{item.skill_id}"),
            "掌握度": round(score * 100, 2),
            "掌握情况": mastery_level(score),
            "知识点id": item.skill_id,
        }
        print(json.dumps(row, ensure_ascii=False))


def main() -> None:
    args = build_parser().parse_args()
    # 命令行参数优先级高于环境变量，环境变量优先级高于默认配置。
    config = ReKTConfig.from_env()
    if args.data_dir:
        config = ReKTConfig(**{**config.__dict__, "data_dir": args.data_dir})
    if args.checkpoint:
        config = ReKTConfig(**{**config.__dict__, "checkpoint_path": args.checkpoint})
    if args.device:
        config = ReKTConfig(**{**config.__dict__, "device": args.device})

    diagnoser = ReKTDiagnoser(config)
    result = diagnoser.diagnose_user(args.user_id, history_limit=args.history_limit, skill_id=args.skill_id)
    print_diagnosis(result, diagnoser.data.skill_names)


if __name__ == "__main__":
    main()
