export type ModuleName = 'cognitive_diagnosis' | 'learning_path';
export type ModuleState = 'pending' | 'running' | 'completed' | 'error' | 'timeout' | 'incomplete' | 'interrupted';
export interface Snapshot {
  output: Record<string, unknown> | null;
  state: ModuleState;
  historical: boolean;
  durationMs?: number;
  message: string;
}
export interface KnowledgePoint {
  id: string;
  name: string;
  mastery: number | null;
  status: 'mastered' | 'developing' | 'weak' | 'unknown';
  evidence: string;
  relevanceRank?: number;
  relevanceTier?: 'related' | 'extended';
  relevanceReason?: string;
}
export interface DiagnosisData {
  studentId: string;
  topic: string;
  summary: string;
  source: string;
  points: KnowledgePoint[];
  actions: string[];
  weakCount: number;
}
export interface PlanStage {
  id: string;
  name: string;
  objective: string;
  reason: string;
  checkpoints: string[];
  outcome: string;
  duration: string;
}
export interface PlanData {
  studentId: string;
  target: string;
  targetId: string;
  estimatedTime: string;
  rationale: string;
  stages: PlanStage[];
}

/** Structural inputs keep this module independent of React and store imports. */
interface TraceInput {
  content: unknown;
  label?: string;
  updatedAt?: string;
}
interface TimelineInput {
  agentName: string;
  status: string;
  startedAt?: number;
  durationMs?: number;
  output?: unknown;
}
interface TurnInput {
  startedAt: number;
  endedAt?: number;
  agentTimeline: readonly TimelineInput[];
}

function record(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}
function text(value: unknown): string {
  return typeof value === 'string' ? value : '';
}
function identifier(value: unknown): string {
  return typeof value === 'number' && Number.isFinite(value) ? String(value) : text(value);
}
function rows(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.map(record).filter((entry) => entry !== null) : [];
}
function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((entry): entry is string => typeof entry === 'string' && entry.length > 0) : [];
}
function firstRows(...values: unknown[]): Record<string, unknown>[] {
  for (const value of values) {
    const entries = rows(value);
    if (entries.length > 0) return entries;
  }
  return [];
}
function probability(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1 ? value : null;
}

export function normalizeDiagnosis(output: unknown): DiagnosisData {
  const data = record(output) ?? {};
  const graph = record(data.knowledge_graph);
  const rates = record(data.mastery_rates) ?? {};
  const points = firstRows(data.knowledge_states, graph?.nodes).map((entry): KnowledgePoint => {
    const id = identifier(entry.skill_id ?? entry.knowledge_point_id ?? entry.id);
    const mastery = probability(entry.mastery_rate ?? entry.mastery ?? rates[id]);
    return {
      id,
      name: text(entry.skill_name ?? entry.knowledge_point_name ?? entry.name ?? entry.label),
      mastery,
      status: mastery === null ? 'unknown' : mastery < 0.4 ? 'weak' : mastery < 0.7 ? 'developing' : 'mastered',
      evidence: text(entry.evidence),
      ...(typeof entry.relevance_rank === 'number' && Number.isInteger(entry.relevance_rank) && entry.relevance_rank > 0 ? { relevanceRank: entry.relevance_rank } : {}),
      ...(entry.relevance_tier === 'related' || entry.relevance_tier === 'extended' ? { relevanceTier: entry.relevance_tier } : {}),
      ...(text(entry.relevance_reason) ? { relevanceReason: text(entry.relevance_reason) } : {}),
    };
  });
  return {
    studentId: identifier(data.kt_student_id ?? data.student_id),
    topic: text(data.topic_analysis),
    summary: text(data.diagnosis_summary),
    source: data.diagnosis_source === 'kt' ? 'KT' : text(data.diagnosis_source),
    points,
    actions: strings(data.recommended_actions),
    weakCount: points.filter((point) => point.status === 'weak').length,
  };
}

export function normalizePlan(output: unknown): PlanData {
  const data = record(output) ?? {};
  const target = record(data.target) ?? {};
  const suppliedStages = firstRows(data.learning_path, data.stages);
  const usingRecommendedPoints = suppliedStages.length === 0;
  const entries = usingRecommendedPoints ? rows(data.recommended_knowledge_points) : suppliedStages;
  const stages = entries.map((entry, index): PlanStage => {
    const minutes = entry.duration_min;
    const skillReasons = rows(entry.skills).map((skill) => text(skill.reason)).filter(Boolean);
    return {
      id: identifier(entry.stage_id ?? (usingRecommendedPoints
        ? `P${typeof entry.order === 'number' && Number.isInteger(entry.order) && entry.order > 0 ? entry.order : index + 1}`
        : entry.id)),
      name: text(entry.name ?? entry.knowledge_point_name),
      objective: text(entry.objective),
      reason: text(entry.reason) || skillReasons.join('\n'),
      checkpoints: strings(entry.checkpoints),
      outcome: text(entry.expected_outcome ?? entry.outcome),
      duration: text(entry.duration) || (typeof minutes === 'number' && Number.isFinite(minutes) && minutes >= 0 ? `${minutes}分钟` : ''),
    };
  });
  return {
    studentId: identifier(data.lpp_student_id ?? data.student_id),
    target: text(target.question_text),
    targetId: identifier(target.question_id),
    estimatedTime: text(data.total_estimated_time ?? data.estimated_completion),
    rationale: text(data.planning_rationale),
    stages,
  };
}

function parseOutput(value: unknown): Record<string, unknown> | null {
  if (typeof value !== 'string') return record(value);
  try {
    return record(JSON.parse(value));
  } catch {
    return null;
  }
}

const messages: Record<ModuleState, string> = {
  pending: '等待执行',
  running: '正在执行',
  completed: '已完成',
  error: '执行失败',
  timeout: '执行超时',
  incomplete: '结果不完整',
  interrupted: '执行已中断',
};

function outputState(name: ModuleName, output: Record<string, unknown> | null): ModuleState {
  const status = text(output?.status).toLowerCase();
  if (status === 'timeout') return 'timeout';
  if (status === 'error' || status === 'failed' || output?.error) return 'error';
  if (!output) return 'incomplete';
  if (name === 'cognitive_diagnosis') {
    return normalizeDiagnosis(output).points.length > 0 ? 'completed' : 'incomplete';
  }
  const source = text(output.lpp_source).toLowerCase();
  if (source === 'unavailable' || source === 'lpp_unavailable') return 'error';
  const stages = normalizePlan(output).stages;
  return stages.length === 5 && stages.every((stage) => stage.name.trim().length > 0) ? 'completed' : 'incomplete';
}

export function resolveModuleSnapshot(
  name: ModuleName,
  trace: TraceInput | null | undefined,
  turn: TurnInput | null | undefined,
  currentAgent: string | null | undefined,
  busy: boolean,
): Snapshot {
  const snapshot = (state: ModuleState, output: Record<string, unknown> | null = null, historical = false, durationMs?: number): Snapshot => ({
    output, state, historical,
    ...(typeof durationMs === 'number' && Number.isFinite(durationMs) && durationMs >= 0 ? { durationMs } : {}),
    message: text(output?.message) || messages[state],
  });
  // Search backwards without mutating the timeline: a later retry owns this module.
  const timeline = turn?.agentTimeline ?? [];
  let item: TimelineInput | undefined;
  for (let i = timeline.length - 1; i >= 0; i -= 1) {
    if (timeline[i].agentName === name) {
      item = timeline[i];
      break;
    }
  }
  if (item) {
    if (item.status === 'running') {
      if (!busy) return snapshot('interrupted', null, false, item.durationMs);
      const now = Date.now();
      const start = item.startedAt;
      const elapsed = typeof start === 'number' && Number.isFinite(start) && start >= 0 && start <= now ? now - start : undefined;
      return snapshot('running', null, false, elapsed);
    }
    if (item.status === 'pending') return snapshot('pending');
    let output = parseOutput(item.output);
    // A trace may fill a missing completion only when its timestamp belongs to
    // this turn and this attempt. Invalid explicit node output never falls back.
    if (item.output === undefined && item.status === 'completed' && trace && turn) {
      const updatedAt = Date.parse(trace.updatedAt ?? '');
      if (updatedAt >= Math.max(turn.startedAt, item.startedAt ?? turn.startedAt)) {
        output = parseOutput(trace.content);
      }
    }
    const state = outputState(name, output);
    return snapshot(
      state === 'timeout' || state === 'error' ? state : item.status === 'error' ? 'error' : state,
      output, false, item.durationMs,
    );
  }
  if (busy) return snapshot(currentAgent === name ? 'running' : 'pending');
  if (trace) {
    const output = parseOutput(trace.content);
    return snapshot(outputState(name, output), output, true);
  }
  return snapshot('pending');
}
