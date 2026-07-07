from __future__ import annotations

import argparse
import os
import shlex
import sys
import tomllib
from pathlib import Path

from chat_agent.deep_agent import DeepAgentRuntime, create_chat_deep_agent
from chat_agent.env import env_bool, load_dotenv
from chat_agent.executor import CommandExecutor
from chat_agent.orchestrator import Orchestrator
from chat_agent.router import RuleBasedRouter
from chat_agent.session import ChatSession
from chat_agent.skill_markdown_executor import SkillMarkdownExecutor
from chat_agent.skill_loader import SkillLoader
from chat_agent.skill_registry import SkillRegistry
from chat_agent.validator import SkillExecutionValidator


DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "skills.toml"


def build_runtime(config_path: str | Path = DEFAULT_CONFIG):
    load_dotenv()
    config = _load_config(config_path)
    kt_config = config["skills"]["kt_runtime"]
    skill_path = Path(kt_config["path"])
    skills = SkillLoader([skill_path]).load()
    allowed_prefixes = _allowed_prefixes_from_skills(skills)

    executor = CommandExecutor(
        allowed_prefixes=allowed_prefixes,
        default_timeout=int(config.get("execution", {}).get("timeout_seconds", 120)),
    )
    skill_executor = SkillMarkdownExecutor(executor=executor, timeout=int(config.get("execution", {}).get("timeout_seconds", 120)))
    registry = SkillRegistry(skill_executor=skill_executor)
    for skill in skills:
        registry.register(skill)

    orchestrator = Orchestrator(
        registry=registry,
        router=RuleBasedRouter(),
        validator=SkillExecutionValidator(),
    )
    return orchestrator, skills, config


def build_chat_runtime(config_path: str | Path = DEFAULT_CONFIG):
    orchestrator, skills, config = build_runtime(config_path)
    mode = _agent_mode(config)
    if mode == "rules":
        return orchestrator, skills, config
    return DeepAgentRuntime(orchestrator=orchestrator, skills=skills, config=config), skills, config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ChatAgent local skill runtime")
    parser.add_argument("message", nargs="*", help="User message to handle")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--deepagents", action="store_true", help="Build a DeepAgents harness before handling")
    args = parser.parse_args(argv)

    runtime, skills, config = build_chat_runtime(args.config)
    if args.deepagents:
        model = config.get("llm", {}).get("model") or None
        skill_sources = config.get("deepagents", {}).get("skill_sources", [])
        create_chat_deep_agent(runtime.orchestrator if hasattr(runtime, "orchestrator") else runtime, skills, model=model, skill_sources=skill_sources)

    message = " ".join(args.message).strip()
    if not message:
        return _interactive_loop(runtime)

    result = runtime.handle_message(message)
    print(result.final_response)
    return 0 if result.status in {"ok", "need_input", "no_skill", "cancelled"} else 1


def _interactive_loop(orchestrator) -> int:
    session = ChatSession()
    while True:
        try:
            message = input("> ").strip()
        except EOFError:
            return 0
        if message in {"exit", "quit"}:
            return 0
        if not message:
            continue
        print(orchestrator.handle_message(message, session=session).final_response)


def _load_config(path: str | Path):
    with Path(path).open("rb") as handle:
        return tomllib.load(handle)


def _allowed_prefixes_from_skills(skills):
    prefixes: list[list[str]] = []
    for skill in skills:
        for entrypoint in skill.policy.default_entrypoints:
            prefixes.append(shlex.split(entrypoint))
    if prefixes:
        return prefixes
    return [["conda", "run", "-n", "kt", "python", "scripts/run_kt.py"]]


def _agent_mode(config) -> str:
    env_mode = ""
    if os.getenv("CHATAGENT_DEEPAGENT_ENABLED") is not None:
        env_mode = "deepagent" if env_bool("CHATAGENT_DEEPAGENT_ENABLED", True) else "rules"
    mode = env_mode or config.get("agent", {}).get("mode", "deepagent")
    return str(mode).strip().lower()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
