from pathlib import Path

from chat_agent.main import build_runtime


def write_skill(skill_dir: Path) -> None:
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        """---
name: kt-runtime-skill
description: Use when 需要基于学生 ID 运行 KT 预测。
---

## Execution

默认用 `conda run -n kt python scripts/run_kt.py` 执行普通 KT 学情分析。

## Forbidden Actions

- 不要访问外部网络
- 不要调用无关的本地服务

## Output

中文报告读取：`llm_analysis.report_markdown`
""",
        encoding="utf-8",
    )


def write_config(config_path: Path, skill_dir: Path) -> None:
    config_path.write_text(
        f"""
[skills.kt_runtime]
name = "kt-runtime-skill"
path = "{skill_dir}"
skill_executor = "skill_markdown"
level = 1

[execution]
timeout_seconds = 120

[agent]
mode = "rules"
""",
        encoding="utf-8",
    )


def test_runtime_uses_skill_policy_for_skill_executor_and_command_allowlist(tmp_path: Path):
    skill_dir = tmp_path / "kt-runtime-skill"
    write_skill(skill_dir)
    config_path = tmp_path / "skills.toml"
    write_config(config_path, skill_dir)

    orchestrator, skills, _config = build_runtime(config_path)

    assert orchestrator.registry.skill_executor is not None
    assert orchestrator.registry.skill_executor.executor.allowed_prefixes == [
        ["conda", "run", "-n", "kt", "python", "scripts/run_kt.py"]
    ]
