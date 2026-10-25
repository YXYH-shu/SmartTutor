/**
 * 课题 4.3 可视化：视图模型类型。
 *
 * 适配层（safetyAdapter / correctorAdapter）把后端 trace 的原始 JSON 转成这里的结构，
 * 组件只消费视图模型，不直接读原始字段。这样：
 *  - 后端字段缺失、类型不对时，适配层统一兜底，组件不会崩；
 *  - 不接 API 的历史案例演示，只要把原始 JSON 传给组件即可复用。
 */

export type Json = Record<string, unknown>;

/* ── 安全监测 ───────────────────────────────────────────── */

export type SafetyBranch = 'PASS' | 'REJECT' | 'GUIDE';
export type SafetyIntent = 'learning' | 'emotional' | 'probing' | 'malicious';

export interface SafetyPerceptionView {
  /** 本轮是否做了新的风险分类；false 表示承接上一轮的判断 */
  classifiedThisTurn: boolean;
  riskDetected: boolean | null;
  category: string; // N / A / B / C / D1 / D2 / D3 / ''
  categoryLabel: string;
  severity: string; // none / low / moderate / high ...
  severityLabel: string;
  coreTopic: string;
  originalQuery: string;
  confidence: number | null;
}

export interface SafetyIntentView {
  intent: SafetyIntent | '';
  intentLabel: string;
  operationalRequest: boolean | null;
  repeatProbe: boolean | null;
  crisisDetected: boolean | null;
  requestType: string;
  requestTypeLabel: string;
}

export interface SafetyValueView {
  branch: SafetyBranch | '';
  teachable: boolean | null;
  decisionSource: string;
  decisionSourceLabel: string;
  policyLabel: string;
  forbidden: string[];
  allowed: string[];
  rejectType: string;
}

export interface SafetySubjectOption {
  key: string;
  label: string;
  focus: string;
  safeQuery: string;
  learningOptions: string[];
  recommended: string;
}

export interface SafetyGuidanceView {
  triggered: boolean;
  /** subject = 正在选学科；focus = 正在选知识焦点 */
  phase: 'subject' | 'focus' | '';
  coreTopic: string;
  subjects: SafetySubjectOption[];
  selectedSubjectLabel: string;
  focusOptions: string[];
  recommendedOption: string;
  fallback: boolean;
  fallbackReason: string;
}

export interface SafetyTransformView {
  triggered: boolean;
  originalQuery: string;
  safeGoal: string;
  safeQuery: string;
  summary: string;
  constraints: string[];
  preserved: string[];
}

/**
 * classified      本轮做了完整的风险分类（学生的自由提问）
 * subject_chosen  学生点选了学科视角（确定性匹配，不做风险分类）
 * focus_chosen    学生点选了知识焦点，安全监测放行进入教学
 */
export type SafetyMode = 'classified' | 'subject_chosen' | 'focus_chosen';

export interface SafetyView {
  mode: SafetyMode;
  /** 学生本轮点选的选项原文（仅 subject_chosen / focus_chosen） */
  selectionText: string;
  branch: SafetyBranch | '';
  branchLabel: string;
  perception: SafetyPerceptionView;
  intent: SafetyIntentView;
  value: SafetyValueView;
  guidance: SafetyGuidanceView;
  transform: SafetyTransformView;
  directResponse: string;
}

/* ── 内容矫正 ───────────────────────────────────────────── */

export type CorrectorAction = 'PASS' | 'PATCH' | 'REGENERATE';

export interface CorrectorDimensionView {
  key: string;
  label: string;
  /** 0-100；后端未提供时为 null */
  score: number | null;
  /** 该维度的说明（来自 dimension_notes 或 issue_details），没有则为空 */
  note: string;
  /** 模型摘录的原文依据（后端已校验确实出现在原回答中），没有则为空 */
  evidence: string;
  hasIssue: boolean;
}

export interface CorrectorPatchView {
  before: string;
  after: string;
  reason: string;
}

export interface CorrectorIssueView {
  dimensionLabel: string;
  problem: string;
  reason: string;
}

export interface CorrectorLegacyCheck {
  key: string;
  label: string;
  /** 该项验收标准（来自内容矫正提示词的验收标准原文） */
  criterion: string;
  passed: boolean | null;
}

export interface CorrectorView {
  action: CorrectorAction | '';
  requestedAction: CorrectorAction | '';
  statusLabel: string;
  severity: 'none' | 'minor' | 'major' | '';
  severityLabel: string;
  summary: string;
  dimensions: CorrectorDimensionView[];
  hasScores: boolean;
  legacyChecks: CorrectorLegacyCheck[];
  passedCount: number;
  totalChecks: number;
  issues: CorrectorIssueView[];
  patches: CorrectorPatchView[];
  patchedText: string;
  changeRatio: number | null;
  structurePreserved: boolean | null;
  regenerationCount: number;
}
