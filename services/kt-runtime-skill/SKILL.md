---
name: kt-runtime-skill
description: Use when 用户明确要求对某个学生 ID 做 KT 学情分析、知识点掌握度诊断报告，或预测该学生的知识点掌握情况；仅提供学生 ID、身份声明或普通学习问答时不要使用。
---

# KT Runtime Skill

## Purpose

Use this skill to run the local KT knowledge tracing runtime for a student ID and produce a Chinese learning diagnosis report. The report has two parts:

- Deterministic KT data from the runtime: knowledge points, mastery percentages, mastery statuses, and selected knowledge point details.
- Agent-written natural language analysis: only the marked block in `## 3. 学情分析结果`, written from runtime materials and the bundled style template.

## When to Use

Use this skill when the user asks for:

- 学情分析 / 学习情况分析 / 学习诊断
- KT prediction / knowledge tracing
- 知识点掌握度预测或诊断
- 基于某个学生 ID 的中文学习报告

Do not use this skill for ordinary learning Q&A, general study advice, or when the user only states an identity such as “我是学生 ID 40”.

## Runtime Command

Work from the skill directory:

```bash
cd services/kt-runtime-skill
```

Default student-ID mode requires:

- `student_id`: numeric ID such as `40`

默认用 `conda run -n kt python scripts/run_kt.py` 执行普通 KT 学情分析。

Default student-ID analysis:

```bash
conda run -n kt python scripts/run_kt.py --student-id 40
```

Include `--history-context` only when the user has already provided learning context:

```bash
conda run -n kt python scripts/run_kt.py \
  --student-id 40 \
  --history-context "学生最近在学电路，刚询问了闭合回路为什么才能让小灯泡亮起来。"
```

Do not ask the user for answer sequences. Student-ID mode derives history from the local KT dataset.

## Runtime Facts

- Stable Agent-facing entrypoint: `scripts/run_kt.py`
- Default runtime config: `config/runtime.toml`
- Runtime backend: bundled KT CLI at `scripts/kt_runtime/kt_engine/cli.py`
- Dataset: bundled KT data at `assets/kt/dataset`
- Checkpoint: bundled KT checkpoint at `assets/kt/checkpoint/kt.pt`
- Default device: `cuda:0`; if CUDA is unavailable, bundled KT inference automatically falls back to CPU.
- `skill_id` in runtime data means KT `kp_id`.
- Default prediction target is all KT-predictable knowledge points. Catalog-only knowledge points without question mappings are not prediction targets.

If the command returns `status: error`, do not fabricate a report. Explain the runtime error briefly.

## Important Output Fields

The CLI writes one JSON object to stdout. For normal reporting, use these fields:

- `status`: `ok` or `error`
- `predictions`: full KT prediction rows
- `metrics`: aggregate runtime metrics
- `model_info`: runtime metadata
- `llm_analysis.report_markdown`: Markdown report template with stable sections and an Agent rewrite marker
- `llm_analysis.agent_revision_task`: materials and requirements for the Agent-written natural language analysis
- `llm_analysis.mastery_table`: selected report rows with `skill_id`, `source_skill_id`, `knowledge_point_name`, `predicted_mastery`, `mastery_status`, and `evidence`
- `llm_analysis.selected_knowledge_points`: selected knowledge point details

Use runtime values exactly. Do not invent or alter mastery percentages, statuses, knowledge point IDs, knowledge point names, history statistics, or risk labels.

## Report Structure

The user-facing report must preserve this structure:

1. `## 1. 主题判定`
2. `## 2. 知识点集合`
3. `## 3. 学情分析结果`
4. `## 4. 诊断知识点明细`

Only the marked natural-language block in section 3 is Agent-written. Sections 1, 2, the mastery table in section 3, and section 4 must remain unchanged from `llm_analysis.report_markdown`.

## Filling the Natural Language Block

中文报告读取：`llm_analysis.report_markdown`，再用 `llm_analysis.agent_revision_task` 替换 Agent rewrite marker。

Start from `llm_analysis.report_markdown`. Replace only the text between:

```markdown
<!-- AGENT_REWRITE_REQUIRED_BEGIN -->
...
<!-- AGENT_REWRITE_REQUIRED_END -->
```

Write the replacement from `llm_analysis.agent_revision_task`:

- Use `source_materials` as the factual source.
- Use `style_template` as the writing style reference. The same template is also embedded inside the rewrite marker in `llm_analysis.report_markdown` so callers that pass only `report_markdown` still expose it to the model.
- Follow the embedded Markdown template's section structure, tone, and analysis style.
- Base the analysis on selected knowledge points, KT mastery values, mastery statuses, knowledge point descriptions, learning context, and history summary.
- Teaching suggestions should be concrete and tied to weak or developing knowledge points.
- Output only the section 3 body. The first line of the replacement block must be exactly `### 3.1 总体学情概述`.
- Do not output any text before `### 3.1 总体学情概述`: no report title, opening explanation, horizontal rule, or sentence such as "根据返回的 KT 诊断结果，以下是替换后的自然语言分析与教学建议".
- Do not add a closing note such as "report sections remain unchanged".

Final answer assembly rules:

- Return the full report after replacement, not only the natural-language analysis block.
- Preserve every part of `llm_analysis.report_markdown` outside the rewrite marker, including section headings, knowledge point tables, the mastery table, and selected knowledge point details.
- Remove the marker comments and the embedded reference template from the final user-facing report. They are drafting instructions only.
- Do not reorder sections, rename fixed report sections, drop tables, or summarize section 4.
- If the final answer contains only the rewritten natural-language block, it is incomplete.

The bundled natural language style template lives at:

`assets/report-templates/learning-analysis-style-template.md`

The template is a style and structure reference only. Its example numbers, knowledge points, module names, and proportions are not facts for the current student. Do not output the template itself in the final report; use it only to shape the rewritten natural-language analysis.

## Table Contracts

`## 2. 知识点集合` uses only:

`知识点ID | 知识点名称 | 类型`

The mastery table in `## 3. 学情分析结果` uses only:

`知识点ID | 知识点名称 | 预测掌握度 | 掌握状态 | 判断依据`

Rules:

- Knowledge point names should come from `assets/kt/dataset/knowledges.json` by matching `id` to runtime `skill_id`; fall back to `exercise_info.json.kp_desc` only when catalog names are unavailable.
- `预测掌握度` must come from the KT CLI `掌握度` field.
- `掌握状态` must come from the KT CLI `掌握情况` field.
- `判断依据` should be `-` when no dedicated evidence field is available.
- Do not add an `优先级` column.

## Do Not Expose Internals

In user-facing reports, do not mention:

- internal selected row counts or phrases such as “为你选出 N 条”
- n-gram similarity, selection scores, matched terms, backend parameters, or model-field provenance
- implementation details of the KT CLI, dataset plumbing, or report renderer

## Development Notes

These notes apply only when the user explicitly asks to inspect, modify, debug, or integrate the runtime.

- Keep `scripts/run_kt.py` as the stable Agent-facing command.
- Keep KT inference self-contained inside this skill. Do not reintroduce dependencies on an external KT project directory.
- The bundled KT inference code lives in `scripts/kt_runtime/kt_engine/`.
- Bundled KT assets live in `assets/kt/`.
- Report generation lives in `scripts/kt_runtime/analysis_report.py`.
- The style template asset is `assets/report-templates/learning-analysis-style-template.md`.
- Run focused tests after report changes:

```bash
python3 -m unittest tests/test_analysis_report.py
```

- Run all tests before claiming completion:

```bash
python3 -m unittest discover -s tests
```

For ordinary student analysis, do not modify files, bypass `scripts/run_kt.py`, directly import runtime modules, hand-build low-level KT request JSON, or ask the user for answer sequences.
