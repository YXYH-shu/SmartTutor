# Runtime contract

## Successful transformation

```json
{
  "status": "ok",
  "education_domain": "science_safety",
  "selection_mode": "two_stage",
  "safe_query": "关于电击对动物的影响，可以从哪些学科角度安全地学习？",
  "learning_options": [
    "物理：理解电流、导电与能量转化",
    "生物：理解电流对动物生命活动的影响"
  ],
  "recommended_option": "生物：理解电流对动物生命活动的影响",
  "subject_options": [
    {
      "school_subject": "physics",
      "label": "物理：理解电流、导电与能量转化",
      "subject_focus": "电流路径、电阻与能量转化",
      "safe_query": "电流在不同材料中的传导与能量转化有什么规律？",
      "learning_options": ["比较导体与绝缘体", "理解电阻对电流的影响"],
      "recommended_option": "理解电阻对电流的影响"
    },
    {
      "school_subject": "biology",
      "label": "生物：理解电流对动物生命活动的影响",
      "subject_focus": "神经、肌肉与循环系统的电生理反应",
      "safe_query": "电流为什么会影响动物的神经、肌肉和心脏功能？",
      "learning_options": ["分析神经信号受到的影响", "理解心脏电活动与循环功能"],
      "recommended_option": "分析神经信号受到的影响"
    }
  ],
  "preserved_elements": [
    "原问题中被原样保留的主体",
    "原问题中被原样保留的提问意图"
  ],
  "transformation_summary": "一句话说明剥离了什么风险并保留了什么学习目标",
  "constraints_applied": [
    "未提供危险操作步骤",
    "未提供可执行参数"
  ]
}
```

`status` must be `ok`; this Skill is invoked only after the safety classifier has determined that
the request is teachable. Every successful call must provide the complete two-stage structure.

- `education_domain` must be one of `science_safety`, `history_civics`, `law_ethics`, `digital_literacy`, `health_wellbeing`, `interpersonal`, `age_appropriate`, or `general`.
- `selection_mode` must be `two_stage`; one-stage GUIDE output is invalid.
- `school_subject` must be one of `primary_science`, `chinese_language`, `mathematics`,
  `physics`, `chemistry`, `biology`, `history`, `geography`, `ethics_and_rule_of_law`,
  `information_technology`, `health_education`, `labor_and_technology`, or `interdisciplinary`.
- In `two_stage`, `subject_options` must contain two or three branches with distinct
  `school_subject` values. Every branch must provide `label`, `subject_focus`, `safe_query`, two
  or three `learning_options`, and a matching `recommended_option`.
- In `two_stage`, top-level `learning_options` must exactly equal the branch labels, and top-level
  `recommended_option` must equal one branch label.
- `safe_query` must be non-empty.
- `learning_options` must contain two or three distinct non-empty strings.
- `recommended_option` must exactly match one item in `learning_options`.
- `preserved_elements` must contain exact substrings retained from `original_query` in `safe_query`.
- `safe_query` and every option must preserve a clear semantic anchor from `core_topic`; repeating the entire `core_topic` verbatim is not required.
- Options must be specific to the selected education domain and must not be a generic risk-label menu.
- Every branch's `safe_query` and options must stay within its own `school_subject` and `subject_focus`.
- The recommended option must be the nearest safe continuation of the original task, not merely the safest-sounding general topic.
- If the original requests a safe artifact or output form after removing the risky fragment, preserve that output form.
- `transformation_summary` must describe the minimal semantic change in neutral language; it must not be a refusal, warning, or emotional judgment.
- `constraints_applied` must name only constraints actually applied to this transformation.
- Constraints describe risk-enabling uses, not banned word classes. Safe materials, measurements,
  low-risk parameters, and procedures remain valid output when needed for an independently safe task.

## Quality interpretation

- **Topic preserved**: the same subject, object, named entities, scope, and requested relation remain wherever safe.
- **Intent preserved**: design, explain, compare, analyze, evaluate, or create remains the same task type wherever safe.
- **Minimum repair**: only the fragment that grants unsafe capability is deleted, abstracted, or safely substituted.
- **Specific options**: each option names a concrete subtask grounded in the current question and could not be pasted unchanged onto an unrelated topic.
- **Answerable**: a downstream education agent can directly produce a substantive response without first repairing the option again.
