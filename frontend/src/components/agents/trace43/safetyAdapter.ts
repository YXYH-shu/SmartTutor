/**
 * 安全监测 trace → 视图模型。
 * 输入是后端 safety_monitor 的 thinking 内容（已 JSON.parse）。所有读取都容错。
 */
import type {
  Json,
  SafetyBranch,
  SafetyGuidanceView,
  SafetyIntent,
  SafetyIntentView,
  SafetyMode,
  SafetyPerceptionView,
  SafetySubjectOption,
  SafetyTransformView,
  SafetyValueView,
  SafetyView,
} from './types';

export const RISK_CATEGORY_LABELS: Record<string, string> = {
  N: '无风险主题',
  A: '伤害或危险操作',
  B: '学段不适内容',
  C: '现实危机',
  D1: '偏见歧视仇恨',
  D2: '隐私侵害',
  D3: '深度伪造与欺诈',
};

const SEVERITY_LABELS: Record<string, string> = {
  none: '无',
  low: '较低',
  moderate: '中等',
  high: '较高',
  severe: '严重',
};

export const INTENT_LABELS: Record<SafetyIntent, string> = {
  learning: '学习探究',
  emotional: '情绪表达',
  probing: '边界试探',
  malicious: '恶意意图',
};

const REQUEST_TYPE_LABELS: Record<string, string> = {
  benign_information: '正常知识或任务',
  educational_analysis: '原理与防护分析',
  emotional_support: '情绪支持',
  method_request: '索取危险方法',
  intent_statement: '表达实施意图',
  crisis_disclosure: '现实危机表达',
  evasion_request: '索取规避方法',
  unknown: '无法判断',
};

const DECISION_SOURCE_LABELS: Record<string, string> = {
  primary_model: '主模型判断',
  adjudicator_model: '裁决模型复核',
  primary_after_adjudicator_error: '裁决失败，沿用主模型',
  local_fallback: '本地规则兜底',
  deterministic_rule: '确定性规则',
};

const POLICY_LABELS: Record<string, string> = {
  first_turn_method_request_to_guide: '首次方法探询，转为教育引导',
  safety_education_topic_to_guide: '属安全教育主题，转为教育引导',
  provider_content_filter_to_guide: '模型内容过滤，转为教育引导',
  explicit_malicious_request_to_reject: '明确恶意请求，直接拒绝',
  direct_crisis_signal_to_reject: '现实危机信号，安全回应',
  compound_crisis_signal_to_reject: '复合危机信号，安全回应',
  benign_maker_request_to_pass: '无害制作请求，放行',
  neutral_civics_question_to_pass: '中性常识问题，放行',
  general_deepfake_literacy_to_pass: '通用媒介素养，放行',
  benign_analysis_to_pass: '无害分析，放行',
};

export const BRANCH_LABELS: Record<SafetyBranch, string> = {
  PASS: '进入学习',
  REJECT: '安全回应',
  GUIDE: '教育引导',
};

/* ── 小工具 ─────────────────────────────────────────────── */

export function asObject(value: unknown): Json {
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? (value as Json) : {};
}

export function asString(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

export function asBool(value: unknown): boolean | null {
  return typeof value === 'boolean' ? value : null;
}

export function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

export function asStringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string' && item.trim() !== '').map((s) => s.trim())
    : [];
}

function normalizeBranch(value: unknown): SafetyBranch | '' {
  const upper = asString(value).toUpperCase();
  return upper === 'PASS' || upper === 'REJECT' || upper === 'GUIDE' ? upper : '';
}

function normalizeIntent(value: unknown): SafetyIntent | '' {
  const lower = asString(value).toLowerCase();
  return lower === 'learning' || lower === 'emotional' || lower === 'probing' || lower === 'malicious'
    ? lower
    : '';
}

function buildPerception(ctx: Json, classifier: Json, hasClassifier: boolean): SafetyPerceptionView {
  const category = asString(classifier.risk_category) || asString(ctx.risk_category);
  const severity = asString(classifier.harm_severity);
  return {
    classifiedThisTurn: hasClassifier,
    riskDetected: asBool(classifier.risk_detected),
    category,
    categoryLabel: RISK_CATEGORY_LABELS[category] ?? '',
    severity,
    severityLabel: SEVERITY_LABELS[severity] ?? severity,
    coreTopic: asString(ctx.core_topic),
    originalQuery: asString(ctx.original_query),
    confidence: asNumber(classifier.confidence),
  };
}

function buildIntent(ctx: Json, classifier: Json): SafetyIntentView {
  const requestType = asString(classifier.request_type);
  return {
    intent: normalizeIntent(classifier.intent) || normalizeIntent(ctx.intent),
    intentLabel: '',
    operationalRequest: asBool(classifier.operational_request) ?? asBool(ctx.operational_request),
    repeatProbe: asBool(classifier.repeat_probe),
    crisisDetected: asBool(classifier.crisis_detected),
    requestType,
    requestTypeLabel: REQUEST_TYPE_LABELS[requestType] ?? requestType,
  };
}

function buildValue(root: Json, ctx: Json, classifier: Json, branch: SafetyBranch | ''): SafetyValueView {
  const source = asString(classifier.decision_source);
  const policy = asString(classifier.policy_correction);
  const guidance = asObject(ctx.guidance_skill);
  return {
    branch,
    teachable: asBool(classifier.teachable),
    decisionSource: source,
    decisionSourceLabel: DECISION_SOURCE_LABELS[source] ?? source,
    policyLabel: POLICY_LABELS[policy] ?? policy,
    forbidden: asStringList(ctx.forbidden_content),
    allowed: asStringList(ctx.allowed_content),
    rejectType: asString(ctx.reject_type) || asString(guidance.reject_type) || asString(root.reject_type),
  };
}

function buildSubjects(raw: unknown): SafetySubjectOption[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((item, index) => {
      const o = asObject(item);
      return {
        key: asString(o.school_subject) || `subject-${index}`,
        label: asString(o.label),
        focus: asString(o.subject_focus),
        safeQuery: asString(o.safe_query),
        learningOptions: asStringList(o.learning_options),
        recommended: asString(o.recommended_option),
      };
    })
    .filter((s) => s.label !== '');
}

function buildGuidance(ctx: Json, branch: SafetyBranch | ''): SafetyGuidanceView {
  const skill = asObject(ctx.guidance_skill);
  const subjects = buildSubjects(ctx.subject_options ?? skill.subject_options);
  const phaseRaw = asString(ctx.selection_phase) || asString(skill.selection_phase);
  const triggered = Object.keys(skill).length > 0 || subjects.length > 0;
  const phase: SafetyGuidanceView['phase'] = !triggered
    ? ''
    : phaseRaw === 'focus'
      ? 'focus'
      : 'subject';
  return {
    triggered: triggered && branch !== 'REJECT',
    phase,
    coreTopic: asString(ctx.core_topic),
    subjects,
    selectedSubjectLabel: asString(ctx.selected_subject_label) || asString(skill.selected_subject_label),
    focusOptions: asStringList(ctx.learning_options ?? skill.learning_options),
    recommendedOption: asString(ctx.recommended_option) || asString(skill.recommended_option),
    fallback: asString(skill.status) === 'fallback',
    fallbackReason: asString(ctx.fallback_reason) || asString(ctx.skill_error_code),
  };
}

function buildTransform(ctx: Json, guidanceTriggered: boolean): SafetyTransformView {
  const skill = asObject(ctx.guidance_skill);
  const safeGoal = asString(ctx.safe_learning_goal);
  return {
    triggered: guidanceTriggered && safeGoal !== '',
    originalQuery: asString(ctx.original_query),
    safeGoal,
    safeQuery: asString(ctx.safe_query) || asString(skill.safe_query),
    summary: asString(skill.transformation_summary),
    constraints: asStringList(skill.constraints_applied),
    preserved: asStringList(skill.preserved_elements),
  };
}

/** 入口：把 safety_monitor 的原始输出转成视图模型。传入非对象时返回空视图。 */
export function buildSafetyView(raw: unknown): SafetyView {
  const root = asObject(raw);
  const ctx = asObject(root.safety_context);
  const classifier = asObject(ctx.classifier);
  const hasClassifier = Object.keys(classifier).length > 0;
  const branch = normalizeBranch(root.raw_branch) || normalizeBranch(ctx.branch);

  const perception = buildPerception(ctx, classifier, hasClassifier);
  const intent = buildIntent(ctx, classifier);
  intent.intentLabel = intent.intent ? INTENT_LABELS[intent.intent] : '';
  const guidance = buildGuidance(ctx, branch);

  const selectedOption = asString(ctx.selected_option);
  const selectedSubject = asString(ctx.selected_subject_label) || asString(asObject(ctx.guidance_skill).selected_subject_label);
  let mode: SafetyMode = 'classified';
  let selectionText = '';
  if (!hasClassifier) {
    if (ctx.resolved_from_guide === true || selectedOption) {
      mode = 'focus_chosen';
      selectionText = selectedOption;
    } else if (asString(ctx.selection_phase) === 'focus' && selectedSubject) {
      mode = 'subject_chosen';
      selectionText = selectedSubject;
    }
  }

  return {
    mode,
    selectionText,
    branch,
    branchLabel: branch ? BRANCH_LABELS[branch] : '',
    perception,
    intent,
    value: buildValue(root, ctx, classifier, branch),
    guidance,
    transform: buildTransform(ctx, guidance.triggered),
    directResponse: asString(root.direct_response),
  };
}
