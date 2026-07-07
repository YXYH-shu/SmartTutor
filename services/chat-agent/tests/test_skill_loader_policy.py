from pathlib import Path

from chat_agent.policy import extract_policy
from chat_agent.skill_loader import SkillLoader


def test_extract_policy_reads_default_entrypoint_for_kt_skill():
    skill_md = """
---
name: kt-runtime-skill
description: Use when 需要基于学生 ID 运行 KT 预测。
---

## 默认执行规则

- 默认用 `conda run -n kt python scripts/run_kt.py`
- 不要新建 Python 文件
- 不要手工拼底层 KT 请求 JSON
- 中文报告读取：`llm_analysis.report_markdown`
"""

    policy = extract_policy(skill_md)

    assert policy.default_entrypoints == ["conda run -n kt python scripts/run_kt.py"]
    assert "不要新建 Python 文件" in policy.forbidden_actions
    assert "不要手工拼底层 KT 请求 JSON" in policy.forbidden_actions
    assert policy.output_paths == ["llm_analysis.report_markdown"]


def test_extract_policy_keeps_history_context_optional_for_student_id_mode():
    skill_md = """
---
name: kt-runtime-skill
description: Use when 需要基于学生 ID 运行 KT 预测。
---

## Inputs

Default student-ID mode requires:

- `student_id`: numeric ID such as `5`

Optional context:

- `history_context`: optional current learning context for report ranking
- `targets`: optional; omitted means all kp IDs

## Execution

默认用 `conda run -n kt python scripts/run_kt.py` 执行普通 KT 学情分析。
"""

    policy = extract_policy(skill_md)

    assert policy.required_inputs == ["student_id"]


def test_skill_loader_loads_frontmatter_and_policy(tmp_path: Path):
    skill_dir = tmp_path / "kt-runtime-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        """---
name: kt-runtime-skill
description: Use when 需要基于学生 ID 或已知 kp 作答序列运行 KT 预测。
---

## 默认执行规则

- 默认用 `conda run -n kt python scripts/run_kt.py`
- 不要写临时 Python 脚本
- 中文报告读取：`llm_analysis.report_markdown`
""",
        encoding="utf-8",
    )

    skills = SkillLoader([skill_dir]).load()

    assert len(skills) == 1
    skill = skills[0]
    assert skill.name == "kt-runtime-skill"
    assert "KT 预测" in skill.description
    assert skill.path == skill_dir
    assert skill.policy.default_entrypoints == ["conda run -n kt python scripts/run_kt.py"]
    assert "不要写临时 Python 脚本" in skill.policy.forbidden_actions
