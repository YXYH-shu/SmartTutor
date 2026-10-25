import { useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  Activity,
  ArrowDown,
  Boxes,
  Check,
  ChevronLeft,
  CornerDownLeft,
  Database,
  ExternalLink,
  FileText,
  GitBranch,
  Network,
  Orbit,
  RefreshCw,
  Route,
  ScanSearch,
  ShieldCheck,
  SlidersHorizontal,
  X,
  type LucideIcon,
} from 'lucide-react';
import type {
  RecommendedResource,
  ResourceRecommendationOutput,
  ResourceRecommendationPlan,
  ResourceRecommendationReflection,
  ResourceRecommendationToolTrace,
} from '@/types';
import { cn } from '@/utils/cn';

interface Props {
  onBack: () => void;
  onClose: () => void;
  output: ResourceRecommendationOutput | null;
  message?: string;
  isRunning: boolean;
}

interface RankingEvidence {
  trace?: ResourceRecommendationToolTrace;
  fallback?: ResourceRecommendationToolTrace;
  mode: 'personality' | 'similarity' | 'unknown';
  backend: string;
  candidateCount: number | null;
  requestedCount: number | null;
  effectiveCount: number | null;
  candidateSource: string;
  fallbackReason?: string;
}

const REPLAY_DELAYS = [0, 180, 470, 780, 1090];

const TOOL_LABELS: Record<string, string> = {
  SqlRetrievalTool: 'SQL 召回',
  CandidateFallback: '候选回退',
  RankingTool: '排序引擎',
};

const FALLBACK_LABELS: Record<string, string> = {
  sql_not_called: '未执行 SQL，改用完整资源目录',
  sql_empty: 'SQL 没有命中，改用完整资源目录',
  missing_similarity_anchor: '缺少相似度锚点，降级为个性化图排序',
};

function asFiniteNumber(value: unknown): number | null {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  if (typeof value !== 'string' || !value.trim()) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatPercent(value: unknown): string {
  const numeric = asFiniteNumber(value);
  return numeric === null ? '-' : `${Math.round(Math.max(0, Math.min(1, numeric)) * 100)}%`;
}

function scoreFor(resource: RecommendedResource): number | null {
  return asFiniteNumber(resource.similarity_score ?? resource.graph_score);
}

function scoreKind(resource: RecommendedResource): string {
  return resource.similarity_score !== undefined ? '文本相似度' : '图模型分';
}

function formatScore(value: number | null): string {
  return value === null ? '—' : value.toFixed(4);
}

function normalizeScore(value: number | null, maxScore: number | null): number {
  if (value === null || maxScore === null || maxScore <= 0) return 0;
  return Math.max(0, Math.min(1, value / maxScore));
}

function displayBackend(value: string): string {
  if (value === 'graph') return '图模型';
  if (value === 'text_embedding') return '文本嵌入';
  if (value === 'deterministic_fallback') return '确定性回退';
  return value || '待确认';
}

function displayMode(value: RankingEvidence['mode']): string {
  if (value === 'similarity') return '相似资源';
  if (value === 'personality') return '个性化排序';
  return '未触发排序';
}

function getRankingEvidence(traces: ResourceRecommendationToolTrace[]): RankingEvidence {
  const trace = [...traces].reverse().find((item) => item.tool === 'RankingTool');
  const fallback = [...traces].reverse().find((item) => item.tool === 'CandidateFallback');
  const rawMode = trace?.effective_schema || trace?.requested_schema || 'unknown';
  const mode = rawMode === 'similarity' || rawMode === 'personality' ? rawMode : 'unknown';
  return {
    trace,
    fallback,
    mode,
    backend: trace?.ranking_backend || '',
    candidateCount: asFiniteNumber(trace?.candidate_count),
    requestedCount: asFiniteNumber(trace?.requested_num),
    effectiveCount: asFiniteNumber(trace?.effective_num),
    candidateSource: trace?.candidate_source || '',
    fallbackReason: trace?.fallback_reason || fallback?.reason,
  };
}

function MotionStyles() {
  return (
    <style>{`
      @keyframes resource-flow-packet {
        0% { transform: translateY(-12px); opacity: 0; }
        18% { opacity: .95; }
        82% { opacity: .95; }
        100% { transform: translateY(102px); opacity: 0; }
      }
      @keyframes resource-flow-rise {
        from { transform: translateY(8px); opacity: 0; }
        to { transform: translateY(0); opacity: 1; }
      }
      @keyframes resource-flow-sweep {
        from { transform: rotate(-40deg); opacity: .35; }
        50% { opacity: 1; }
        to { transform: rotate(320deg); opacity: .35; }
      }
      @keyframes resource-flow-breathe {
        0%, 100% { opacity: .42; transform: scale(.94); }
        50% { opacity: 1; transform: scale(1); }
      }
      .resource-flow-packet { animation: resource-flow-packet 1.6s linear infinite; }
      .resource-flow-rise { animation: resource-flow-rise .42s ease-out both; }
      .resource-flow-sweep { animation: resource-flow-sweep 1.9s linear infinite; }
      .resource-flow-breathe { animation: resource-flow-breathe 1.9s ease-in-out infinite; }
      @media (prefers-reduced-motion: reduce) {
        .resource-flow-packet, .resource-flow-rise, .resource-flow-sweep, .resource-flow-breathe { animation: none !important; }
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
    <section
      className={cn(
        'relative pl-10 transition-all duration-500 motion-reduce:transition-none',
        visible ? 'translate-y-0 opacity-100' : 'translate-y-2 opacity-20',
      )}
    >
      <span
        className={cn(
          'absolute left-0 top-0 flex h-6 w-6 items-center justify-center rounded-full border transition-colors duration-300',
          visible
            ? 'border-emerald-400/55 bg-emerald-500/15 text-emerald-500 shadow-[0_0_16px_rgba(52,211,153,0.12)] dark:text-emerald-300'
            : 'border-border-subtle bg-bg-base text-text-tertiary',
        )}
      >
        {visible ? <Icon size={13} /> : <span className="font-mono text-[10px]">{index + 1}</span>}
      </span>
      {index < REPLAY_DELAYS.length - 1 && (
        <span className={cn('absolute left-[11px] top-7 h-[calc(100%+0.5rem)] w-px', visible ? 'bg-emerald-400/45' : 'bg-border-subtle')} />
      )}
      <div className="min-w-0 border-b border-border-subtle pb-3.5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-[12px] font-semibold text-text-primary">{title}</p>
            <p className="mt-0.5 text-[10px] text-text-tertiary">{subtitle}</p>
          </div>
          {visible && <Check size={13} className="mt-0.5 shrink-0 text-emerald-500 dark:text-emerald-300" />}
        </div>
        <div className="mt-2.5 min-w-0">{children}</div>
      </div>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: unknown }) {
  const numeric = asFiniteNumber(value);
  const width = numeric === null ? 0 : Math.max(0, Math.min(1, numeric)) * 100;
  return (
    <div className="min-w-0">
      <div className="mb-1 flex items-center justify-between gap-2 font-mono text-[10px] text-text-tertiary">
        <span className="truncate">{label}</span>
        <span className="text-text-secondary">{formatPercent(value)}</span>
      </div>
      <div className="h-1 overflow-hidden rounded-sm bg-bg-base">
        <div className="h-full rounded-sm bg-emerald-500/80 transition-[width] duration-700 motion-reduce:transition-none" style={{ width: `${width}%` }} />
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
      <p className={cn('mt-1 truncate text-[10px] font-medium', accent)}>{value}</p>
    </div>
  );
}

function ExecutionCircuit({
  planHistory,
  reflectionHistory,
  hasSummary,
  isBoundary,
}: {
  planHistory: ResourceRecommendationPlan[];
  reflectionHistory: ResourceRecommendationReflection[];
  hasSummary: boolean;
  isBoundary: boolean;
}) {
  const retryCount = reflectionHistory.filter((item, index) => !item.passed && index + 1 < planHistory.length).length;
  const finalReflection = reflectionHistory[reflectionHistory.length - 1];
  const stages = [
    { label: '规划', icon: Route, active: planHistory.length > 0 || hasSummary },
    { label: '工具', icon: Database, active: !isBoundary && reflectionHistory.length > 0 },
    { label: '反思', icon: ShieldCheck, active: reflectionHistory.length > 0 },
    { label: '汇总', icon: FileText, active: hasSummary && (isBoundary || finalReflection?.passed !== false) },
  ];

  return (
    <section className="relative mt-3.5 border-b border-border-subtle pb-3">
      <div className="mb-2 flex items-center justify-between gap-3 text-[10px] font-medium text-text-secondary">
        <span>执行路径</span>
        <span className={cn('shrink-0 font-mono text-[10px]', retryCount > 0 ? 'text-accent' : 'text-emerald-600 dark:text-emerald-300')}>
          {retryCount > 0 ? `${retryCount} 次回环` : hasSummary ? '已收敛' : '等待证据'}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-1">
        {stages.map(({ label, icon: Icon, active }, index) => (
          <div
            key={label}
            className={cn(
              'flex min-w-0 items-center gap-1.5 rounded-full border px-2 py-1 transition-colors duration-500 motion-reduce:transition-none',
              active
                ? 'border-emerald-400/30 bg-emerald-500/5 text-text-primary'
                : 'border-border-subtle bg-bg-base/45 text-text-tertiary',
            )}
          >
            <span
              className={cn(
                'flex h-5 w-5 shrink-0 items-center justify-center rounded-full border bg-bg-elevated transition-colors duration-500 motion-reduce:transition-none',
                active
                  ? 'border-emerald-400/55 text-emerald-600 shadow-[0_0_14px_rgba(52,211,153,0.14)] dark:text-emerald-300'
                  : 'border-border-subtle text-text-tertiary',
              )}
            >
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

function PlanRounds({ plans }: { plans: ResourceRecommendationPlan[] }) {
  return (
    <div className="mt-2.5 space-y-1.5">
      {plans.map((plan, index) => (
        <div key={`plan-${index}`} className="rounded-lg border border-border-subtle bg-bg-base/65 px-2.5 py-2">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] font-semibold text-text-primary">第 {index + 1} 轮计划</span>
            {plan.target_count !== undefined && <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 font-mono text-[10px] text-emerald-600 dark:text-emerald-300">目标 {plan.target_count} 项</span>}
          </div>
          <p className="mt-1 text-[11px] leading-4 text-text-secondary">{plan.recall_strategy || '未返回召回策略'}</p>
          {(plan.ranking_criteria?.length ?? 0) > 0 && (
            <div className="mt-1.5 flex flex-wrap gap-1 text-[10px] text-text-tertiary">
              {plan.ranking_criteria?.map((criterion) => <span key={`${index}-${criterion}`} className="rounded-full bg-bg-elevated px-2 py-0.5">{criterion}</span>)}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function ReflectionRounds({
  reflections,
  planCount,
}: {
  reflections: ResourceRecommendationReflection[];
  planCount: number;
}) {
  return (
    <div className="mt-3 space-y-2">
      {reflections.map((item, index) => {
        const returnsToPlan = !item.passed && index + 1 < planCount;
        return (
          <div key={`reflection-${index}`} className={cn('border-l pl-2.5', item.passed ? 'border-emerald-400/55' : 'border-accent')}>
            <div className="flex items-center justify-between gap-2">
              <span className={cn('font-mono text-[10px]', item.passed ? 'text-emerald-600 dark:text-emerald-300' : 'text-accent')}>REFLECTION {String(index + 1).padStart(2, '0')}</span>
              <span className={cn('font-mono text-[10px]', item.passed ? 'text-emerald-600 dark:text-emerald-300' : 'text-status-error')}>
                {item.passed ? item.forced_pass ? 'FORCED PASS' : 'PASS' : 'RETURN'}
              </span>
            </div>
            {!item.passed && (item.improvement_suggestion || item.suggestion || item.issues?.[0]) && (
              <p className="mt-1 text-[10px] leading-4 text-text-secondary">{item.improvement_suggestion || item.suggestion || item.issues?.[0]}</p>
            )}
            {returnsToPlan && (
              <p className="mt-1.5 flex items-center gap-1 font-mono text-[10px] text-accent">
                <CornerDownLeft size={11} /> 返回 Plan {String(index + 2).padStart(2, '0')}
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}

function ResourceSignalCard({ resource, index, maxScore }: { resource: RecommendedResource; index: number; maxScore: number | null }) {
  const score = scoreFor(resource);
  const scoreWidth = normalizeScore(score, maxScore);
  const rank = resource.rank ?? index + 1;
  const metadata = [
    resource.type,
    resource.difficulty,
    typeof resource.time_needed_min === 'number' ? `${resource.time_needed_min} 分钟` : undefined,
  ].filter((value): value is string => Boolean(value));

  return (
    <article className="resource-flow-rise rounded-lg border border-border-subtle bg-bg-base/80 px-3 py-2.5 shadow-[0_6px_18px_rgba(0,0,0,0.06)]" style={{ animationDelay: `${index * 90}ms` }}>
      <div className="flex items-start gap-2">
        <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-md border border-accent/30 bg-accent-soft font-mono text-[10px] text-accent">
          {String(rank).padStart(2, '0')}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <p className="min-w-0 text-[11px] font-semibold leading-4 text-text-primary">{resource.title || '未命名资源'}</p>
            {resource.url && (
              <a
                href={resource.url}
                target="_blank"
                rel="noreferrer"
                className="shrink-0 text-text-tertiary transition-colors hover:text-accent"
                title="打开资源"
                aria-label={`打开资源：${resource.title}`}
              >
                <ExternalLink size={11} />
              </a>
            )}
          </div>
          {metadata.length > 0 && (
            <div className="mt-1.5 flex flex-wrap gap-1 text-[10px] text-text-tertiary">
              {metadata.map((item) => <span key={item} className="rounded-full bg-bg-elevated px-1.5 py-0.5">{item}</span>)}
            </div>
          )}
          <div className="mt-2 border-t border-border-subtle pt-1.5">
            <div className="mb-1 flex items-center justify-between gap-2 text-[10px] text-text-tertiary">
              <span>{scoreKind(resource)}</span>
              <span className="font-mono text-text-secondary">{formatScore(score)}</span>
            </div>
            <div className="h-px overflow-hidden bg-bg-elevated">
              <div className="h-full bg-sky-400/85 transition-[width] duration-700 motion-reduce:transition-none" style={{ width: `${scoreWidth * 100}%` }} />
            </div>
          </div>
          {resource.similarity_reference_title && (
            <p className="mt-1.5 flex items-center gap-1 text-[10px] leading-4 text-text-tertiary">
              <GitBranch size={10} className="shrink-0 text-sky-500 dark:text-sky-300" />
              <span className="min-w-0 truncate">锚点：{resource.similarity_reference_title}</span>
            </p>
          )}
          {resource.recommend_reason && (
            <p className="mt-1.5 text-[10px] leading-4 text-text-secondary">
              <span className="mr-1 text-text-tertiary">推荐依据</span>
              {resource.recommend_reason}
            </p>
          )}
        </div>
      </div>
    </article>
  );
}

function ToolEvent({ trace }: { trace: ResourceRecommendationToolTrace }) {
  const isFallback = trace.tool === 'CandidateFallback';
  const label = TOOL_LABELS[trace.tool] || trace.tool;
  const detail = isFallback
    ? FALLBACK_LABELS[trace.reason || ''] || trace.reason || '已应用候选回退'
    : trace.status === 'executed'
      ? '已完成'
      : trace.status || '未触发';
  return (
    <div className="flex min-w-0 items-center gap-2 border-t border-border-subtle py-2 first:border-t-0 first:pt-0">
      <span className={cn('flex h-5 w-5 shrink-0 items-center justify-center rounded-full border', isFallback ? 'border-amber-400/40 bg-accent-soft text-accent' : 'border-sky-400/35 bg-sky-400/10 text-sky-500 dark:text-sky-300')}>
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
    <div className="relative mt-6 overflow-hidden rounded-lg border border-emerald-400/25 bg-emerald-500/5 px-4 py-5 shadow-[0_8px_24px_rgba(16,185,129,0.06)]">
      <div className="flex items-center gap-4">
        <span className="relative flex h-14 w-14 shrink-0 items-center justify-center rounded-full border border-emerald-400/30 bg-bg-base/50 text-emerald-500 dark:text-emerald-300">
          {isRunning && (
            <>
              <span className="resource-flow-breathe absolute inset-2 rounded-full border border-emerald-400/20" />
              <span className="resource-flow-sweep absolute left-1/2 top-1/2 h-px w-5 origin-left bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.72)]" />
            </>
          )}
          <ScanSearch size={18} strokeWidth={1.6} />
        </span>
        <div className="min-w-0">
          <p className="text-[11px] font-semibold text-text-primary">{isRunning ? '正在生成资源推荐' : '本轮暂无资源推荐结果'}</p>
          <p className="mt-1 text-[10px] leading-4 text-text-tertiary">
            {isRunning ? '后端暂不推送阶段进度，任务完成后将显示真实执行轨迹。' : '该智能体尚未在本轮流程中完成执行。'}
          </p>
        </div>
      </div>
    </div>
  );
}

export function ResourceRecommendationFlow({ onBack, onClose, output, message, isRunning }: Props) {
  const [visibleStages, setVisibleStages] = useState(0);
  const [replayKey, setReplayKey] = useState(0);
  const requestMessage = message || '本轮对话的资源推荐请求';

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
  const planning: ResourceRecommendationPlan | undefined = output?.planning ?? rawPlanHistory[rawPlanHistory.length - 1];
  const planHistory = rawPlanHistory.length > 0 ? rawPlanHistory : planning ? [planning] : [];
  const traces = output?.tool_trace ?? [];
  const recallTraces = traces.filter((trace) => trace.tool === 'SqlRetrievalTool' || trace.tool === 'CandidateFallback');
  const evidence = useMemo(() => getRankingEvidence(traces), [traces]);
  const reflectionHistory = output?.reflection_history ?? [];
  const reflection: ResourceRecommendationReflection | undefined = output?.reflection ?? reflectionHistory[reflectionHistory.length - 1];
  const hasReflection = Boolean(reflection && Object.keys(reflection).length > 0);
  const rankedResources = useMemo(() => (output?.resources ?? []).slice(0, 5), [output?.resources]);
  const rankPreview = rankedResources.slice(0, 3);
  const maxScore = useMemo(() => Math.max(...rankedResources.map((resource) => scoreFor(resource) ?? 0), 0) || null, [rankedResources]);
  const fallbackText = evidence.fallbackReason ? FALLBACK_LABELS[evidence.fallbackReason] || evidence.fallbackReason : '';
  const isBoundary = planHistory[planHistory.length - 1]?.need_tool === false;
  const finalReflection = reflectionHistory[reflectionHistory.length - 1];
  const hasSummary = Boolean(output?.recommendation_text || rankedResources.length > 0);
  const summaryAccepted = isBoundary || finalReflection?.passed !== false;

  return (
    <div className="absolute inset-0 z-30 flex flex-col bg-bg-elevated animate-slide-in-right">
      <MotionStyles />
      <div className="flex items-center justify-between border-b border-border-subtle px-4 py-3">
        <div className="flex min-w-0 items-center gap-3">
          <button
            type="button"
            onClick={onBack}
            className="shrink-0 rounded-md p-1.5 text-text-tertiary transition-colors hover:bg-bg-base hover:text-text-primary"
            title="返回智能体面板"
            aria-label="返回智能体面板"
          >
            <ChevronLeft size={16} />
          </button>
          <div className="flex h-8 w-8 shrink-0 items-center justify-center border border-emerald-400/30 bg-emerald-500/10 text-emerald-500 dark:text-emerald-300">
            <Network size={16} />
          </div>
          <div className="min-w-0">
            <h3 className="truncate text-[14px] font-display font-semibold text-text-primary">资源推荐</h3>
            <p className="font-mono text-[10px] text-text-tertiary">RECOMMENDATION TRACE</p>
          </div>
        </div>
        <div className="flex items-center gap-1">
          {output && (
            <button
              type="button"
              onClick={() => setReplayKey((value) => value + 1)}
              className="rounded-md p-1.5 text-text-tertiary transition-colors hover:bg-bg-base hover:text-emerald-500"
              title="重播流程"
              aria-label="重播流程"
            >
              <RefreshCw size={15} />
            </button>
          )}
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1.5 text-text-tertiary transition-colors hover:bg-bg-base hover:text-text-primary"
            title="关闭详情"
            aria-label="关闭详情"
          >
            <X size={16} />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4 scrollbar-thin">
        <section className="relative overflow-hidden rounded-lg border border-border-subtle bg-bg-base/80 p-3 shadow-[0_8px_22px_rgba(0,0,0,0.06)]">
          {isRunning && <span className="resource-flow-packet absolute right-4 top-0 h-1.5 w-1.5 rounded-full bg-emerald-400" />}
          <div className="flex items-center justify-between gap-3">
            <span className="text-[10px] font-medium text-text-secondary">当前会话请求</span>
            <span className={cn('flex shrink-0 items-center gap-1 font-mono text-[10px]', isRunning ? 'text-emerald-600 dark:text-emerald-300' : 'text-text-tertiary')}>
              <span className={cn('h-1.5 w-1.5 rounded-full', isRunning ? 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.75)]' : 'bg-text-tertiary')} />
              {isRunning ? 'LIVE' : output ? 'COMPLETE' : 'IDLE'}
            </span>
          </div>
          <p className="mt-1.5 text-[12px] font-medium leading-5 text-text-primary">{requestMessage}</p>
          <div className="mt-2.5 flex flex-wrap gap-1 text-[10px] text-text-secondary">
            <span className="rounded-full border border-border-subtle bg-bg-elevated px-2 py-0.5">SQL 召回</span>
            <span className="rounded-full border border-border-subtle bg-bg-elevated px-2 py-0.5">{output ? displayMode(evidence.mode) : '排序等待中'}</span>
            {output && evidence.backend && <span className="rounded-full border border-border-subtle bg-bg-elevated px-2 py-0.5">{displayBackend(evidence.backend)}</span>}
          </div>
        </section>

        {output ? (
          <div className="mt-5 space-y-5">
            <ExecutionCircuit
              planHistory={planHistory}
              reflectionHistory={reflectionHistory}
              hasSummary={hasSummary}
              isBoundary={isBoundary}
            />

            <Stage index={0} title="Plan" subtitle={`${planHistory.length || 1} 轮规划`} icon={Route} visible={visibleStages >= 1}>
              {planHistory.length > 0 ? <PlanRounds plans={planHistory} /> : <p className="text-[10px] text-text-tertiary">本轮未返回 Plan 证据。</p>}
            </Stage>

            <Stage index={1} title="工具执行 · SQL" subtitle={`${recallTraces.length} 次真实调用`} icon={ScanSearch} visible={visibleStages >= 2}>
              {recallTraces.length > 0 ? (
                <div className="border-y border-border-subtle py-2">
                  {recallTraces.map((trace, index) => <ToolEvent key={`${trace.tool}-${index}`} trace={trace} />)}
                </div>
              ) : (
                <p className="text-[10px] leading-4 text-text-tertiary">本轮计划未调用 SQL 召回，排序引擎将按运行结果处理候选集。</p>
              )}
            </Stage>

            <Stage index={2} title="工具执行 · 排序" subtitle={`${displayMode(evidence.mode)} · ${displayBackend(evidence.backend)}`} icon={SlidersHorizontal} visible={visibleStages >= 3}>
              <div className="grid grid-cols-2 gap-2">
                <EvidenceTile icon={Orbit} label="排序模式" value={displayMode(evidence.mode)} accent="text-sky-600 dark:text-sky-300" />
                <EvidenceTile icon={Boxes} label="候选来源" value={evidence.candidateSource || '未返回'} />
                <EvidenceTile icon={Database} label="候选数量" value={evidence.candidateCount === null ? '—' : `${evidence.candidateCount}`} />
                <EvidenceTile icon={Activity} label="返回数量" value={evidence.effectiveCount === null ? `${rankedResources.length}` : `${evidence.effectiveCount}`} />
              </div>
              {fallbackText && (
                <div className="mt-3 flex items-start gap-2 border-l-2 border-accent bg-accent-soft/40 px-2.5 py-2 text-[10px] leading-4 text-text-secondary">
                  <ArrowDown size={13} className="mt-0.5 shrink-0 text-accent" />
                  <span>{fallbackText}</span>
                </div>
              )}
              {evidence.requestedCount !== null && evidence.requestedCount !== evidence.effectiveCount && (
                <p className="mt-2 font-mono text-[10px] text-text-tertiary">
                  请求 {evidence.requestedCount} 项，实际按 {evidence.trace?.num_policy || '运行策略'} 返回 {evidence.effectiveCount ?? rankedResources.length} 项
                </p>
              )}
              {rankPreview.length > 0 ? (
                <div className="mt-3 space-y-2">
                  <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-wide text-text-tertiary">
                    <span className="h-px flex-1 bg-border-subtle" />
                    Rank signal
                    <span className="h-px flex-1 bg-border-subtle" />
                  </div>
                  <div className="space-y-2">
                    {rankPreview.map((resource, index) => <ResourceSignalCard key={`${resource.id}-${resource.similarity_reference_id ?? 'personal'}-${index}`} resource={resource} index={index} maxScore={maxScore} />)}
                  </div>
                </div>
              ) : (
                <p className="mt-3 text-[10px] text-text-tertiary">本轮未返回可排序资源。</p>
              )}
            </Stage>

            <Stage index={3} title="质量校验" subtitle={`${reflectionHistory.length} 轮 Reflection`} icon={ShieldCheck} visible={visibleStages >= 4}>
              {isBoundary ? (
                <p className="text-[10px] leading-4 text-text-tertiary">本轮被识别为非资源推荐请求，跳过工具执行与 Reflection，直接输出边界说明。</p>
              ) : hasReflection ? (
                <div className="space-y-3">
                  <div className="grid grid-cols-3 gap-2">
                    <Metric label="覆盖" value={reflection.coverage_score} />
                    <Metric label="难度" value={reflection.difficulty_match} />
                    <Metric label="多样" value={reflection.diversity_score} />
                  </div>
                  <div className={cn('flex items-center gap-1.5 text-[10px]', reflection.passed ? 'text-emerald-600 dark:text-emerald-300' : 'text-status-error')}>
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

            <Stage index={4} title="推荐汇总" subtitle={summaryAccepted ? (isBoundary ? '边界分支输出' : reflectionHistory.length > 0 ? 'Reflection 放行后的最终输出' : '已完成推荐输出') : '等待 Reflection 放行'} icon={FileText} visible={visibleStages >= 5}>
              {summaryAccepted && hasSummary ? (
                <>
                  <p className="border-l-2 border-emerald-400/70 bg-emerald-500/5 px-3 py-2 text-[11px] leading-5 text-text-secondary">
                    {output.recommendation_text || '本轮未返回推荐文案。'}
                  </p>
                  {rankedResources.length > 0 && (
                    <div className="mt-3 space-y-2">
                      {rankedResources.map((resource, index) => <ResourceSignalCard key={`summary-${resource.id}-${resource.similarity_reference_id ?? 'personal'}-${index}`} resource={resource} index={index} maxScore={maxScore} />)}
                    </div>
                  )}
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

export default ResourceRecommendationFlow;
