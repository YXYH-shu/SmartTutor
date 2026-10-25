/**
 * 内容矫正 trace → 视图模型（V2.0 / V2.5 通用）。
 *
 * V2.5 新增字段（scores / severity / issue_details / patches / summary / change_ratio，
 * 以及可选的 dimension_notes）缺失时，退化为 V2.0 的四项布尔验收展示。
 */
import { asBool, asNumber, asObject, asString } from './safetyAdapter';
import type {
  CorrectorAction,
  CorrectorDimensionView,
  CorrectorIssueView,
  CorrectorLegacyCheck,
  CorrectorPatchView,
  CorrectorView,
  Json,
} from './types';

/** 演示脚本使用的四个评估维度（V2.5 scores 的键） */
export const DIMENSIONS: Array<{ key: string; label: string }> = [
  { key: 'scientific_argumentation', label: '科学论证' },
  { key: 'metacognitive_guidance', label: '元认知引导' },
  { key: 'scientific_discourse', label: '科学话语' },
  { key: 'content_safety', label: '内容安全' },
];

/** V2.0 的四项布尔验收（checks 的键），与上面的维度不是同一套 */
const LEGACY_CHECKS: Array<{ key: string; label: string; criterion: string }> = [
  { key: 'scientific_reliability', label: '科学可靠性', criterion: '事实、概念、术语和因果关系正确，不编造证据、数据或来源' },
  { key: 'educational_completeness', label: '教育完整性', criterion: '直接回答学生问题，解释充分，含必要的结论、原理、例子与适用边界' },
  { key: 'structural_clarity', label: '结构清晰度', criterion: '信息较多时有标题、编号或列表形成层级，原有结构被保留' },
  { key: 'content_safety', label: '内容安全性', criterion: '遵守安全约束，不增加危险操作细节，不绕过上游安全决策' },
];

const STATUS_LABELS: Record<string, string> = {
  passed: '检查通过',
  patched: '已局部修正',
  audited: '已验收',
  patch_rejected: '修改超出范围，退回重写',
  regeneration_limit: '已达重写上限，保留当前结果',
  audit_fallback: '验收服务异常，保留原回答',
};

const SEVERITY_LABELS: Record<string, string> = { none: '无', minor: '轻微', major: '严重' };

function normalizeAction(value: unknown): CorrectorAction | '' {
  const upper = asString(value).toUpperCase();
  return upper === 'PASS' || upper === 'PATCH' || upper === 'REGENERATE' ? upper : '';
}

function dimensionLabel(key: string): string {
  return DIMENSIONS.find((d) => d.key === key)?.label ?? '';
}

function buildIssues(root: Json): CorrectorIssueView[] {
  const details = Array.isArray(root.issue_details) ? root.issue_details : [];
  const fromDetails = details
    .map((item) => {
      const o = asObject(item);
      return {
        dimensionLabel: dimensionLabel(asString(o.dimension)),
        problem: asString(o.problem),
        reason: asString(o.reason),
      };
    })
    .filter((i) => i.problem !== '');
  if (fromDetails.length > 0) return fromDetails;
  // V2.0：只有字符串形式的 issues
  const plain = Array.isArray(root.issues) ? root.issues : [];
  return plain
    .filter((s): s is string => typeof s === 'string' && s.trim() !== '')
    .map((problem) => ({ dimensionLabel: '', problem: problem.trim(), reason: '' }));
}

function buildPatches(root: Json): CorrectorPatchView[] {
  if (!Array.isArray(root.patches)) return [];
  return root.patches
    .map((item) => {
      const o = asObject(item);
      return { before: asString(o.before), after: asString(o.after), reason: asString(o.reason) };
    })
    .filter((p) => p.before !== '' && p.after !== '');
}

function buildDimensions(root: Json, issues: CorrectorIssueView[]): CorrectorDimensionView[] {
  const scores = asObject(root.scores);
  const notes = asObject(root.dimension_notes);
  const evidence = asObject(root.dimension_evidence);
  const detailsByKey = new Map<string, string>();
  if (Array.isArray(root.issue_details)) {
    for (const item of root.issue_details) {
      const o = asObject(item);
      const key = asString(o.dimension);
      const text = asString(o.problem);
      if (key && text && !detailsByKey.has(key)) detailsByKey.set(key, text);
    }
  }
  return DIMENSIONS.map(({ key, label }) => {
    const score = asNumber(scores[key]);
    const issueText = detailsByKey.get(key) ?? '';
    return {
      key,
      label,
      score: score === null ? null : Math.max(0, Math.min(100, Math.round(score))),
      note: asString(notes[key]) || issueText,
      evidence: asString(evidence[key]),
      hasIssue: issueText !== '' || issues.some((i) => i.dimensionLabel === label),
    };
  });
}

function buildLegacyChecks(root: Json): CorrectorLegacyCheck[] {
  const checks = asObject(root.checks);
  return LEGACY_CHECKS.map(({ key, label, criterion }) => ({ key, label, criterion, passed: asBool(checks[key]) }));
}

/** 入口：把 content_corrector 的原始输出转成视图模型。传入非对象时返回空视图。 */
export function buildCorrectorView(raw: unknown): CorrectorView {
  const root = asObject(raw);
  // 引擎偶尔会把结果包在 content_corrector 键下
  const data = Object.keys(asObject(root.content_corrector)).length > 0 ? asObject(root.content_corrector) : root;

  const issues = buildIssues(data);
  const dimensions = buildDimensions(data, issues);
  const legacyChecks = buildLegacyChecks(data);
  const severityRaw = asString(data.severity);
  const severity = severityRaw === 'none' || severityRaw === 'minor' || severityRaw === 'major' ? severityRaw : '';
  const status = asString(data.status);
  const patches = buildPatches(data);
  const knownChecks = legacyChecks.filter((c) => c.passed !== null);

  return {
    action: normalizeAction(data.action),
    requestedAction: normalizeAction(data.requested_action),
    statusLabel: STATUS_LABELS[status] ?? status,
    severity,
    severityLabel: SEVERITY_LABELS[severity] ?? '',
    summary: asString(data.summary),
    dimensions,
    hasScores: dimensions.some((d) => d.score !== null),
    legacyChecks,
    passedCount: knownChecks.filter((c) => c.passed === true).length,
    totalChecks: knownChecks.length,
    issues,
    patches,
    patchedText: asString(data.patched_response),
    changeRatio: asNumber(data.change_ratio),
    structurePreserved: asBool(data.structure_preserved),
    regenerationCount: asNumber(data.regeneration_count) ?? 0,
  };
}
