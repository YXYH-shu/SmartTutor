import { useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  ArrowDown,
  Check,
  ChevronLeft,
  CornerDownLeft,
  Database,
  FileText,
  Network,
  RefreshCw,
  Route,
  ScanSearch,
  ShieldCheck,
  SlidersHorizontal,
  Users,
  X,
  type LucideIcon,
} from 'lucide-react';
import type {
  RecommendedBuddy,
  StudyBuddyOutput,
  StudyBuddyPlan,
  StudyBuddyReflection,
  StudyBuddyToolTrace,
} from '@/types';
import { cn } from '@/utils/cn';

interface Props {
  onBack: () => void;
  onClose: () => void;
  output: StudyBuddyOutput | null;
  message?: string;
  isRunning: boolean;
}

interface RankingEvidence {
  trace?: StudyBuddyToolTrace;
  fallback?: StudyBuddyToolTrace;
  schema: 'personality' | 'similarity' | 'unknown';
  backend: string;
  candidateSource: string;
  candidateCount: number | null;
  eligibleCount: number | null;
  effectiveCount: number | null;
  requestedCount: number | null;
  fallbackReason?: string;
}

const REPLAY_DELAYS = [0, 180, 470, 780, 1090];

const TOOL_LABELS: Record<string, string> = {
  SqlRetrievalTool: 'SQL 候选召回',
  CandidateFallback: '候选回退',
  RankingTool: '图匹配引擎',
};

const FALLBACK_LABELS: Record<string, string> = {
  sql_not_called: '未执行 SQL，改用全量可用学伴',
  sql_empty: 'SQL 未命中候选，改用全量可用学伴',
};

function asNumber(value: unknown): number | null {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  if (typeof value !== 'string' || !value.trim()) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function percent(value: unknown): string {
  const numeric = asNumber(value);
  return numeric === null ? '-' : `${Math.round(Math.max(0, Math.min(1, numeric)) * 100)}%`;
}

function normalized(value: number | null, max: number | null): number {
  if (value === null || max === null || max <= 0) return 0;
  return Math.max(0, Math.min(1, value / max));
}

function displaySchema(value: RankingEvidence['schema']): string {
  if (value === 'personality') return '个性化图匹配';
  if (value === 'similarity') return '相似学伴匹配';
  return '未触发匹配';
}

function displayBackend(value: string): string {
  if (value === 'graph') return '图匹配';
  if (value === 'graph_similarity') return '图相似';
  if (value === 'deterministic_fallback') return '确定性回退';
  return value || '未返回';
}

function buddyScore(buddy: RecommendedBuddy): number | null {
  return asNumber(buddy.complement_score ?? buddy.graph_score ?? buddy.similarity_score);
}

function buddyScoreLabel(buddy: RecommendedBuddy): string {
  if (buddy.complement_score !== undefined) return '互补匹配';
  if (buddy.similarity_score !== undefined) return '相似匹配';
  return '图匹配分';
}

function getRankingEvidence(traces: StudyBuddyToolTrace[]): RankingEvidence {
  const trace = [...traces].reverse().find((item) => item.tool === 'RankingTool');
  const fallback = [...traces].reverse().find((item) => item.tool === 'CandidateFallback');
  const rawSchema = trace?.effective_schema || trace?.requested_schema || 'unknown';
  const schema = rawSchema === 'personality' || rawSchema === 'similarity' ? rawSchema : 'unknown';
  return {
    trace,
    fallback,
    schema,
    backend: trace?.ranking_backend || '',
    candidateSource: trace?.candidate_source || '',
    candidateCount: asNumber(trace?.candidate_count),
    eligibleCount: asNumber(trace?.eligible_candidate_count),
    effectiveCount: asNumber(trace?.effective_num),
    requestedCount: asNumber(trace?.requested_num),
    fallbackReason: trace?.fallback_reason || fallback?.reason,
  };
}

function groupSuggestionText(groupSuggestion?: Record<string, unknown>): string {
  if (!groupSuggestion) return '';
  const preferredKeys = ['formation_strategy', 'suggestion', 'description', 'strategy', 'summary'];
  for (const key of preferredKeys) {
    const value = groupSuggestion[key];
    if (typeof value === 'string' && value.trim()) return value;
  }
  return '';
}

function MotionStyles() {
  return (
    <style>{`
      @keyframes buddy-flow-rise {
        from { transform: translateY(6px); opacity: 0; }
        to { transform: translateY(0); opacity: 1; }
      }
      @keyframes buddy-flow-sweep {
        from { transform: rotate(-40deg); opacity: .35; }
        50% { opacity: 1; }
        to { transform: rotate(320deg); opacity: .35; }
      }
      @keyframes buddy-flow-breathe {
        0%, 100% { opacity: .42; transform: scale(.94); }
        50% { opacity: 1; transform: scale(1); }
      }
      .buddy-flow-rise { animation: buddy-flow-rise .42s ease-out both; }
      .buddy-flow-sweep { animation: buddy-flow-sweep 1.9s linear infinite; }
      .buddy-flow-breathe { animation: buddy-flow-breathe 1.9s ease-in-out infinite; }
      @media (prefers-reduced-motion: reduce) {
        .buddy-flow-rise, .buddy-flow-sweep, .buddy-flow-breathe { animation: none !important; }
      }
    `}</style>
  );
}

function Stage({
  index,
  title,
  subtitle,
  icon: Icon,
  visible,
  children,
}: {
  index: number;
  title: string;
  subtitle: string;
  icon: LucideIcon;
  visible: boolean;
  children: ReactNode;
}) {
  return (
    <section className={cn('relative pl-10 transition-all duration-500 motion-reduce:transition-none', visible ? 'translate-y-0 opacity-100' : 'translate-y-2 opacity-20')}>
      <span className={cn('absolute left-0 top-0 flex h-6 w-6 items-center justify-center rounded-full border transition-colors duration-300', visible ? 'border-cyan-400/55 bg-cyan-500/15 text-cyan-600 shadow-[0_0_16px_rgba(34,211,238,0.12)] dark:text-cyan-300' : 'border-border-subtle bg-bg-base text-text-tertiary')}>
        {visible ? <Icon size={13} /> : <span className="font-mono text-[10px]">{index + 1}</span>}
      </span>
      {index < REPLAY_DELAYS.length - 1 && <span className={cn('absolute left-[11px] top-7 h-[calc(100%+0.5rem)] w-px', visible ? 'bg-cyan-400/45' : 'bg-border-subtle')} />}
      <div className="min-w-0 border-b border-border-subtle pb-3.5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-[12px] font-semibold text-text-primary">{title}</p>
            <p className="mt-0.5 text-[10px] text-text-tertiary">{subtitle}</p>
          </div>
          {visible && <Check size={13} className="mt-0.5 shrink-0 text-cyan-600 dark:text-cyan-300" />}
        </div>
        <div className="mt-2.5 min-w-0">{children}</div>
      </div>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: unknown }) {
  const numeric = asNumber(value);
  const width = numeric === null ? 0 : Math.max(0, Math.min(1, numeric)) * 100;
  return (
    <div className="min-w-0">
      <div className="mb-1 flex items-center justify-between gap-1 font-mono text-[10px] text-text-tertiary">
        <span className="truncate">{label}</span>
        <span className="text-text-secondary">{percent(value)}</span>
      </div>
      <div className="h-1 overflow-hidden rounded-sm bg-bg-base">
        <div className="h-full rounded-sm bg-cyan-500/80 transition-[width] duration-700 motion-reduce:transition-none" style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}

function EvidenceTile({ icon: Icon, label, value, accent = 'text-text-primary' }: { icon: LucideIcon; label: string; value: string; accent?: string }) {
  return (
    <div className="min-w-0 rounded-lg border border-border-subtle bg-bg-base/70 px-2.5 py-2">
      <div className="flex items-center gap-1.5 font-mono text-[10px] text-text-tertiary">
        <Icon size={11} />
        <span className="truncate">{label}</span>
      </div>
      <p className={cn('mt-1 truncate text-[11px] font-medium', accent)}>{value}</p>
    </div>
  );
}

function ExecutionCircuit({
  planHistory,
  reflectionHistory,
  hasSummary,
  isBoundary,
}: {
  planHistory: StudyBuddyPlan[];
  reflectionHistory: StudyBuddyReflection[];
  hasSummary: boolean;
  isBoundary: boolean;
}) {
  const retryCount = reflectionHistory.filter((item, index) => !item.passed && index + 1 < planHistory.length).length;
  const finalReflection = reflectionHistory[reflectionHistory.length - 1];
  const stages = [
    { label: '规划', icon: Route, active: planHistory.length > 0 || hasSummary },
    { label: '匹配', icon: Users, active: !isBoundary && reflectionHistory.length > 0 },
    { label: '反思', icon: ShieldCheck, active: reflectionHistory.length > 0 },
    { label: '汇总', icon: FileText, active: hasSummary && (isBoundary || finalReflection?.passed === true) },
  ];

  return (
    <section className="relative mt-3.5 border-b border-border-subtle pb-3">
      <div className="mb-2 flex items-center justify-between gap-3 text-[10px] font-medium text-text-secondary">
        <span>匹配路径</span>
        <span className={cn('shrink-0 font-mono text-[10px]', retryCount > 0 ? 'text-accent' : 'text-cyan-600 dark:text-cyan-300')}>
          {retryCount > 0 ? `${retryCount} 次回环` : hasSummary ? '已收敛' : '等待证据'}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-1">
        {stages.map(({ label, icon: Icon, active }, index) => (
          <div key={label} className={cn('flex min-w-0 items-center gap-1.5 rounded-full border px-2 py-1 transition-colors duration-500 motion-reduce:transition-none', active ? 'border-cyan-400/30 bg-cyan-500/5 text-text-primary' : 'border-border-subtle bg-bg-base/45 text-text-tertiary')}>
            <span className={cn('flex h-5 w-5 shrink-0 items-center justify-center rounded-full border bg-bg-elevated transition-colors duration-500 motion-reduce:transition-none', active ? 'border-cyan-400/55 text-cyan-600 shadow-[0_0_14px_rgba(34,211,238,0.14)] dark:text-cyan-300' : 'border-border-subtle text-text-tertiary')}>
              <Icon size={11} />
            </span>
            <span className={cn('min-w-0 truncate text-[11px] font-medium leading-none', active ? 'text-text-primary' : 'text-text-tertiary')}>{label}</span>
            <span className="ml-auto shrink-0 font-mono text-[10px] text-text-tertiary">{String(index + 1).padStart(2, '0')}</span>
          </div>
        ))}
      </div>
      {retryCount > 0 && (
        <div className="mt-2 flex items-start gap-1.5 rounded-lg border border-accent/25 bg-accent-soft/25 px-2 py-1.5 text-[10px] leading-4 text-text-secondary">
          <CornerDownLeft size={11} className="mt-0.5 shrink-0 text-accent" />
          <span>检测到未通过的 Reflection，反馈已回到下一轮 Plan 后重新执行。</span>
        </div>
      )}
    </section>
  );
}

function PlanRounds({ plans }: { plans: StudyBuddyPlan[] }) {
  return (
    <div className="mt-2.5 space-y-1.5">
      {plans.map((plan, index) => (
        <div key={`plan-${index}`} className="rounded-lg border border-border-subtle bg-bg-base/65 px-2.5 py-2">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] font-semibold text-text-primary">第 {index + 1} 轮计划</span>
            {plan.target_count !== undefined && <span className="rounded-full bg-cyan-500/10 px-2 py-0.5 font-mono text-[10px] text-cyan-600 dark:text-cyan-300">目标 {plan.target_count} 位</span>}
          </div>
          <p className="mt-1 text-[11px] leading-4 text-text-secondary">{plan.recall_strategy || '未返回候选召回策略'}</p>
          {(plan.ranking_criteria?.length ?? 0) > 0 && (
            <div className="mt-1.5 flex flex-wrap gap-1 text-[10px] text-text-tertiary">
              {plan.ranking_criteria?.map((criterion) => <span key={`${index}-${criterion}`} className="rounded-full bg-bg-elevated px-1.5 py-0.5">{criterion}</span>)}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function ReflectionRounds({ reflections, planCount }: { reflections: StudyBuddyReflection[]; planCount: number }) {
  return (
    <div className="mt-2.5 space-y-2">
      {reflections.map((item, index) => {
        const returnsToPlan = !item.passed && index + 1 < planCount;
        return (
          <div key={`reflection-${index}`} className={cn('border-l pl-2.5', item.passed ? 'border-cyan-400/55' : 'border-accent')}>
            <div className="flex items-center justify-between gap-2">
              <span className={cn('font-mono text-[10px]', item.passed ? 'text-cyan-600 dark:text-cyan-300' : 'text-accent')}>REFLECTION {String(index + 1).padStart(2, '0')}</span>
              <span className={cn('font-mono text-[10px]', item.passed ? 'text-cyan-600 dark:text-cyan-300' : 'text-status-error')}>
                {item.passed ? item.forced_pass ? 'FORCED PASS' : 'PASS' : 'RETURN'}
              </span>
            </div>
            {!item.passed && (item.improvement_suggestion || item.suggestion || item.issues?.[0]) && <p className="mt-1 text-[10px] leading-4 text-text-secondary">{item.improvement_suggestion || item.suggestion || item.issues?.[0]}</p>}
            {returnsToPlan && <p className="mt-1.5 flex items-center gap-1 font-mono text-[10px] text-accent"><CornerDownLeft size={11} /> 返回 Plan {String(index + 2).padStart(2, '0')}</p>}
          </div>
        );
      })}
    </div>
  );
}

function BuddyCard({ buddy, index, maxScore }: { buddy: RecommendedBuddy; index: number; maxScore: number | null }) {
  const score = buddyScore(buddy);
  const rank = buddy.rank ?? index + 1;
  const metadata = [buddy.collaboration_mode, ...(buddy.strengths ?? []).slice(0, 2)].filter((value): value is string => Boolean(value));
  return (
    <article className="buddy-flow-rise rounded-lg border border-border-subtle bg-bg-base/80 px-3 py-2.5 shadow-[0_6px_18px_rgba(0,0,0,0.06)]" style={{ animationDelay: `${index * 90}ms` }}>
      <div className="flex items-start gap-2">
        <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-md border border-accent/30 bg-accent-soft font-mono text-[10px] text-accent">{String(rank).padStart(2, '0')}</span>
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-semibold leading-4 text-text-primary">{buddy.nickname || '学习伙伴'}</p>
          {metadata.length > 0 && (
            <div className="mt-1.5 flex flex-wrap gap-1 text-[10px] text-text-tertiary">
              {metadata.map((item) => <span key={item} className="rounded-full bg-bg-elevated px-1.5 py-0.5">{item}</span>)}
            </div>
          )}
          <div className="mt-2 border-t border-border-subtle pt-1.5">
            <div className="mb-1 flex items-center justify-between gap-2 text-[10px] text-text-tertiary">
              <span>{buddyScoreLabel(buddy)}</span>
              <span className="font-mono text-text-secondary">{percent(score)}</span>
            </div>
            <div className="h-px overflow-hidden bg-bg-elevated">
              <div className="h-full bg-cyan-400/85 transition-[width] duration-700 motion-reduce:transition-none" style={{ width: `${normalized(score, maxScore) * 100}%` }} />
            </div>
          </div>
          {buddy.contact_suggestion && <p className="mt-1.5 text-[10px] leading-4 text-text-secondary"><span className="mr-1 text-text-tertiary">协作建议</span>{buddy.contact_suggestion}</p>}
        </div>
      </div>
    </article>
  );
}

function ToolEvent({ trace }: { trace: StudyBuddyToolTrace }) {
  const isFallback = trace.tool === 'CandidateFallback';
  const label = TOOL_LABELS[trace.tool] || trace.tool;
  const detail = isFallback ? FALLBACK_LABELS[trace.reason || ''] || trace.reason || '已应用候选回退' : trace.status === 'executed' ? '已完成' : trace.status || '未触发';
  return (
    <div className="flex min-w-0 items-center gap-2 border-t border-border-subtle py-2 first:border-t-0 first:pt-0">
      <span className={cn('flex h-5 w-5 shrink-0 items-center justify-center rounded-full border', isFallback ? 'border-amber-400/40 bg-accent-soft text-accent' : 'border-cyan-400/35 bg-cyan-400/10 text-cyan-600 dark:text-cyan-300')}>
        {isFallback ? <ArrowDown size={11} /> : <Database size={11} />}
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate font-mono text-[10px] text-text-secondary">{label}</p>
        <p className="truncate text-[10px] text-text-tertiary">{detail}</p>
      </div>
      <span className="shrink-0 font-mono text-[10px] text-text-tertiary">{trace.count ?? 0}</span>
    </div>
  );
}

function WaitingState({ isRunning }: { isRunning: boolean }) {
  return (
    <div className="relative mt-6 overflow-hidden rounded-lg border border-cyan-400/25 bg-cyan-500/5 px-4 py-5 shadow-[0_8px_24px_rgba(34,211,238,0.06)]">
      <div className="flex items-center gap-4">
        <span className="relative flex h-14 w-14 shrink-0 items-center justify-center rounded-full border border-cyan-400/30 bg-bg-base/50 text-cyan-600 dark:text-cyan-300">
          {isRunning && (
            <>
              <span className="buddy-flow-breathe absolute inset-2 rounded-full border border-cyan-400/20" />
              <span className="buddy-flow-sweep absolute left-1/2 top-1/2 h-px w-5 origin-left bg-cyan-400 shadow-[0_0_8px_rgba(34,211,238,0.72)]" />
            </>
          )}
          <Users size={18} strokeWidth={1.6} />
        </span>
        <div className="min-w-0">
          <p className="text-[11px] font-semibold text-text-primary">{isRunning ? '正在生成学伴推荐' : '本轮暂无学伴推荐结果'}</p>
          <p className="mt-1 text-[10px] leading-4 text-text-tertiary">{isRunning ? '后端暂不推送阶段进度，任务完成后将显示真实匹配轨迹。' : '该智能体尚未在本轮流程中完成执行。'}</p>
        </div>
      </div>
    </div>
  );
}

export function StudyBuddyFlow({ onBack, onClose, output, message, isRunning }: Props) {
  const [visibleStages, setVisibleStages] = useState(0);
  const [replayKey, setReplayKey] = useState(0);
  const requestMessage = message || '本轮对话的学伴推荐请求';

  useEffect(() => {
    setVisibleStages(0);
    if (!output) return;
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
      setVisibleStages(REPLAY_DELAYS.length);
      return;
    }
    const timers = REPLAY_DELAYS.map((delay, index) => window.setTimeout(() => setVisibleStages(index + 1), delay));
    return () => timers.forEach((timer) => window.clearTimeout(timer));
  }, [output, replayKey]);

  const rawPlanHistory = output?.plan_history ?? [];
  const planning = output?.planning ?? rawPlanHistory[rawPlanHistory.length - 1];
  const planHistory = rawPlanHistory.length > 0 ? rawPlanHistory : planning ? [planning] : [];
  const traces = output?.tool_trace ?? [];
  const recallTraces = traces.filter((trace) => trace.tool === 'SqlRetrievalTool' || trace.tool === 'CandidateFallback');
  const evidence = useMemo(() => getRankingEvidence(traces), [traces]);
  const reflectionHistory = output?.reflection_history ?? [];
  const reflection = output?.reflection ?? reflectionHistory[reflectionHistory.length - 1];
  const buddies = useMemo(() => (output?.buddies ?? []).slice(0, 5), [output?.buddies]);
  const topBuddies = buddies.slice(0, 3);
  const maxScore = useMemo(() => Math.max(...buddies.map((buddy) => buddyScore(buddy) ?? 0), 0) || null, [buddies]);
  const fallbackText = evidence.fallbackReason ? FALLBACK_LABELS[evidence.fallbackReason] || evidence.fallbackReason : '';
  const isBoundary = planHistory[planHistory.length - 1]?.need_tool === false;
  const finalReflection = reflectionHistory[reflectionHistory.length - 1];
  const hasSummary = Boolean(output?.recommendation_text || buddies.length > 0);
  const summaryAccepted = isBoundary || finalReflection?.passed === true;
  const groupSuggestion = groupSuggestionText(output?.group_suggestion);

  return (
    <div className="absolute inset-0 z-30 flex flex-col bg-bg-elevated animate-slide-in-right">
      <MotionStyles />
      <div className="flex items-center justify-between border-b border-border-subtle px-4 py-3">
        <div className="flex min-w-0 items-center gap-3">
          <button type="button" onClick={onBack} className="shrink-0 rounded-md p-1.5 text-text-tertiary transition-colors hover:bg-bg-base hover:text-text-primary" title="返回智能体面板" aria-label="返回智能体面板">
            <ChevronLeft size={16} />
          </button>
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-cyan-400/30 bg-cyan-500/10 text-cyan-600 dark:text-cyan-300">
            <Users size={16} />
          </div>
          <div className="min-w-0">
            <h3 className="truncate text-[14px] font-display font-semibold text-text-primary">学伴推荐</h3>
            <p className="font-mono text-[10px] text-text-tertiary">BUDDY MATCH TRACE</p>
          </div>
        </div>
        <div className="flex items-center gap-1">
          {output && (
            <button type="button" onClick={() => setReplayKey((value) => value + 1)} className="rounded-md p-1.5 text-text-tertiary transition-colors hover:bg-bg-base hover:text-cyan-600 dark:hover:text-cyan-300" title="重播流程" aria-label="重播流程">
              <RefreshCw size={15} />
            </button>
          )}
          <button type="button" onClick={onClose} className="rounded-md p-1.5 text-text-tertiary transition-colors hover:bg-bg-base hover:text-text-primary" title="关闭详情" aria-label="关闭详情">
            <X size={16} />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4 scrollbar-thin">
        <section className="relative overflow-hidden rounded-lg border border-border-subtle bg-bg-base/80 p-3 shadow-[0_8px_22px_rgba(0,0,0,0.06)]">
          <div className="flex items-center justify-between gap-3">
            <span className="text-[10px] font-medium text-text-secondary">当前会话请求</span>
            <span className={cn('flex shrink-0 items-center gap-1 font-mono text-[10px]', isRunning ? 'text-cyan-600 dark:text-cyan-300' : 'text-text-tertiary')}>
              <span className={cn('h-1.5 w-1.5 rounded-full', isRunning ? 'bg-cyan-400 shadow-[0_0_8px_rgba(34,211,238,0.75)]' : 'bg-text-tertiary')} />
              {isRunning ? 'LIVE' : output ? 'COMPLETE' : 'IDLE'}
            </span>
          </div>
          <p className="mt-1.5 text-[12px] font-medium leading-5 text-text-primary">{requestMessage}</p>
          <div className="mt-2.5 flex flex-wrap gap-1 text-[10px] text-text-secondary">
            <span className="rounded-full border border-border-subtle bg-bg-elevated px-2 py-0.5">SQL 召回</span>
            <span className="rounded-full border border-border-subtle bg-bg-elevated px-2 py-0.5">{output ? displaySchema(evidence.schema) : '匹配等待中'}</span>
            {output && evidence.backend && <span className="rounded-full border border-border-subtle bg-bg-elevated px-2 py-0.5">{displayBackend(evidence.backend)}</span>}
          </div>
        </section>

        {output ? (
          <div className="mt-5 space-y-5">
            <ExecutionCircuit planHistory={planHistory} reflectionHistory={reflectionHistory} hasSummary={hasSummary} isBoundary={isBoundary} />

            <Stage index={0} title="Plan" subtitle={`${planHistory.length || 1} 轮规划`} icon={Route} visible={visibleStages >= 1}>
              {planHistory.length > 0 ? <PlanRounds plans={planHistory} /> : <p className="text-[10px] text-text-tertiary">本轮未返回 Plan 证据。</p>}
            </Stage>

            <Stage index={1} title="工具执行 · SQL" subtitle={`${recallTraces.length} 次真实调用`} icon={ScanSearch} visible={visibleStages >= 2}>
              {recallTraces.length > 0 ? (
                <div className="border-y border-border-subtle py-2">
                  {recallTraces.map((trace, index) => <ToolEvent key={`${trace.tool}-${index}`} trace={trace} />)}
                </div>
              ) : (
                <p className="text-[10px] leading-4 text-text-tertiary">本轮计划未调用 SQL 召回，匹配引擎将按运行结果处理候选集。</p>
              )}
            </Stage>

            <Stage index={2} title="工具执行 · 匹配" subtitle={`${displaySchema(evidence.schema)} · ${displayBackend(evidence.backend)}`} icon={SlidersHorizontal} visible={visibleStages >= 3}>
              <div className="grid grid-cols-2 gap-2">
                <EvidenceTile icon={Users} label="匹配模式" value={displaySchema(evidence.schema)} accent="text-cyan-700 dark:text-cyan-300" />
                <EvidenceTile icon={Database} label="候选来源" value={evidence.candidateSource || '未返回'} />
                <EvidenceTile icon={Network} label="候选数量" value={evidence.candidateCount === null ? '—' : `${evidence.candidateCount}`} />
                <EvidenceTile icon={ShieldCheck} label="合格候选" value={evidence.eligibleCount === null ? `${buddies.length}` : `${evidence.eligibleCount}`} />
              </div>
              {fallbackText && (
                <div className="mt-3 flex items-start gap-2 border-l-2 border-accent bg-accent-soft/40 px-2.5 py-2 text-[10px] leading-4 text-text-secondary">
                  <ArrowDown size={13} className="mt-0.5 shrink-0 text-accent" />
                  <span>{fallbackText}</span>
                </div>
              )}
              {evidence.requestedCount !== null && evidence.requestedCount !== evidence.effectiveCount && (
                <p className="mt-2 font-mono text-[10px] text-text-tertiary">请求 {evidence.requestedCount} 位，实际按 {evidence.trace?.num_policy || '运行策略'} 返回 {evidence.effectiveCount ?? buddies.length} 位</p>
              )}
              {topBuddies.length > 0 ? (
                <div className="mt-3 space-y-2">
                  <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-wide text-text-tertiary"><span className="h-px flex-1 bg-border-subtle" />Match signal<span className="h-px flex-1 bg-border-subtle" /></div>
                  <div className="space-y-2">{topBuddies.map((buddy, index) => <BuddyCard key={`${buddy.user_id}-${index}`} buddy={buddy} index={index} maxScore={maxScore} />)}</div>
                </div>
              ) : (
                <p className="mt-3 text-[10px] text-text-tertiary">本轮未返回可匹配学伴。</p>
              )}
            </Stage>

            <Stage index={3} title="质量校验" subtitle={`${reflectionHistory.length} 轮 Reflection`} icon={ShieldCheck} visible={visibleStages >= 4}>
              {isBoundary ? (
                <p className="text-[10px] leading-4 text-text-tertiary">本轮被识别为非学伴推荐请求，跳过工具执行与 Reflection，直接输出边界说明。</p>
              ) : reflection ? (
                <div className="space-y-3">
                  <div className="grid grid-cols-3 gap-2">
                    <Metric label="覆盖" value={reflection.coverage_score} />
                    <Metric label="匹配" value={reflection.compatibility_score} />
                    <Metric label="多样" value={reflection.diversity_score} />
                  </div>
                  <div className={cn('flex items-center gap-1.5 text-[10px]', reflection.passed ? 'text-cyan-700 dark:text-cyan-300' : 'text-status-error')}>
                    <ShieldCheck size={12} />
                    <span>{reflection.passed ? '校验通过' : '校验未通过'}</span>
                    {reflection.forced_pass && <span className="font-mono text-[10px] text-text-tertiary">FORCED</span>}
                  </div>
                  {!reflection.passed && reflection.improvement_suggestion && <p className="text-[10px] leading-4 text-text-secondary">{reflection.improvement_suggestion}</p>}
                  {reflectionHistory.length > 0 && <ReflectionRounds reflections={reflectionHistory} planCount={planHistory.length} />}
                </div>
              ) : (
                <p className="text-[10px] text-text-tertiary">本轮未触发 Reflection。</p>
              )}
            </Stage>

            <Stage index={4} title="学伴汇总" subtitle={summaryAccepted ? isBoundary ? '边界分支输出' : 'Reflection 放行后的最终输出' : '等待 Reflection 放行'} icon={FileText} visible={visibleStages >= 5}>
              {summaryAccepted && hasSummary ? (
                <>
                  <p className="border-l-2 border-cyan-400/70 bg-cyan-500/5 px-3 py-2 text-[11px] leading-5 text-text-secondary">{output.recommendation_text || '本轮未返回推荐文案。'}</p>
                  {groupSuggestion && <p className="mt-2 text-[10px] leading-4 text-text-secondary"><span className="mr-1 text-text-tertiary">组队建议</span>{groupSuggestion}</p>}
                  {buddies.length > 0 && <div className="mt-3 space-y-2">{buddies.map((buddy, index) => <BuddyCard key={`summary-${buddy.user_id}-${index}`} buddy={buddy} index={index} maxScore={maxScore} />)}</div>}
                </>
              ) : (
                <p className="text-[10px] leading-4 text-text-tertiary">尚未获得通过的 Reflection 证据，Summary 不展示为最终推荐。</p>
              )}
            </Stage>
          </div>
        ) : (
          <WaitingState isRunning={isRunning} />
        )}
      </div>
    </div>
  );
}

export default StudyBuddyFlow;
