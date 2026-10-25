/**
 * 内容矫正可视化：四维评估 → 定点修正 → 质量自检（按 320px 右栏设计）。
 *
 * - ContentCorrectorView：只依赖原始 trace，可脱离 store / API 单独使用（历史案例演示）。
 * - ContentCorrectorFlow：套上抽屉外壳，供 AgentDetailDrawer 使用。
 * - V2.5 字段缺失时自动退化为 V2.0 的四项布尔验收，不会报错。
 */
import { useMemo } from 'react';
import {
  ArrowDown,
  BadgeCheck,
  ClipboardCheck,
  FilePenLine,
  FlaskConical,
  Lightbulb,
  MessageSquareQuote,
  Microscope,
  PenLine,
  RefreshCcw,
  ShieldCheck,
  Sparkles,
  type LucideIcon,
} from 'lucide-react';
import { cn } from '@/utils/cn';
import { AnimatedBar, delay, useCountUp } from './motion';
import { buildCorrectorView } from './correctorAdapter';
import { CorrectorMechanism } from './MechanismFlow';
import { Chip, EmptyState, Field, FlowShell, Panel, ResultBanner, Stage, TONE_BAR, TONE_TEXT, type Tone } from './primitives';
import type { CorrectorAction, CorrectorDimensionView, CorrectorView } from './types';

const ACTION_TONE: Record<CorrectorAction, Tone> = { PASS: 'success', PATCH: 'warning', REGENERATE: 'error' };
const ACTION_ICON: Record<CorrectorAction, LucideIcon> = { PASS: ShieldCheck, PATCH: FilePenLine, REGENERATE: RefreshCcw };
const ACTION_LABEL: Record<CorrectorAction, string> = { PASS: '检查通过', PATCH: '局部修正', REGENERATE: '退回重写' };
const DIM_ICON: Record<string, LucideIcon> = {
  scientific_argumentation: FlaskConical,
  metacognitive_guidance: Lightbulb,
  scientific_discourse: MessageSquareQuote,
  content_safety: ShieldCheck,
};

function scoreTone(score: number | null, hasIssue: boolean): Tone {
  if (score === null) return hasIssue ? 'warning' : 'neutral';
  if (score >= 90 && !hasIssue) return 'success';
  if (score >= 80) return 'accent';
  return 'warning';
}

function bannerFor(view: CorrectorView): { tone: Tone; icon: LucideIcon; title: string; text: string } | null {
  if (!view.action) return null;
  const tone = ACTION_TONE[view.action];
  const icon = ACTION_ICON[view.action];
  if (view.action === 'PASS') {
    const ok = view.totalChecks > 0 && view.passedCount === view.totalChecks;
    return { tone, icon, title: '验收通过，原文放行', text: ok ? `四项验收 ${view.passedCount}/${view.totalChecks} 全部达标。` : '未发现需要修改的问题，原回答放行。' };
  }
  if (view.action === 'PATCH') {
    const ratio = view.changeRatio === null ? '' : `，改动约 ${Math.round(view.changeRatio * 1000) / 10}%`;
    return { tone, icon, title: '局部修正后放行', text: `仅修正 ${view.patches.length || 1} 处${ratio}，其余内容与结构保留。` };
  }
  return { tone, icon, title: '退回重写', text: view.issues[0]?.problem ? `问题清单已交回知识回复智能体：${view.issues[0].problem}` : '问题清单已交回知识回复智能体重写。' };
}

function DimensionCard({ dim, index }: { dim: CorrectorDimensionView; index: number }) {
  const tone = scoreTone(dim.score, dim.hasIssue);
  const Icon = DIM_ICON[dim.key] ?? Sparkles;
  const shown = useCountUp(dim.score ?? 0, 900, 250 + index * 120);
  return (
    <div className="t43-rise rounded-md border border-border-subtle bg-bg-base p-2.5 transition-colors hover:border-border-strong" style={delay(index, 110, 250)}>
      <div className="flex items-center gap-2">
        <span className={cn('flex h-6 w-6 shrink-0 items-center justify-center rounded-md border', tone === 'success' ? 'border-status-success/30 bg-status-success/10' : 'border-accent/30 bg-accent-soft', TONE_TEXT[tone])}>
          <Icon size={13} strokeWidth={1.75} />
        </span>
        <span className="flex-1 text-12 font-medium text-text-primary">{dim.label}</span>
        <span className={cn('font-mono text-16 font-semibold tabular-nums', TONE_TEXT[tone])}>
          {dim.score === null ? '—' : shown}
          {dim.score !== null && <span className="ml-0.5 text-11 font-normal text-text-tertiary">分</span>}
        </span>
      </div>
      {dim.score !== null && <AnimatedBar percent={dim.score} barClassName={TONE_BAR[tone]} startDelay={250 + index * 120} className="mt-2" />}
      {dim.note && <p className="mt-2 text-11 leading-relaxed text-text-secondary">{dim.note}</p>}
      {dim.evidence && (
        <p className="mt-1.5 border-l-2 border-accent/40 pl-2 text-11 leading-relaxed text-text-tertiary">原文依据：“{dim.evidence}”</p>
      )}
    </div>
  );
}

function EvaluationStage({ view }: { view: CorrectorView }) {
  return (
    <Stage index={1} title="四维评估" subtitle="科学论证 · 元认知引导 · 科学话语 · 内容安全" icon={Microscope}>
      {view.hasScores ? (
        <div className="space-y-2">
          {view.dimensions.map((dim, idx) => (
            <DimensionCard key={dim.key} dim={dim} index={idx} />
          ))}
        </div>
      ) : (
        <Panel className="space-y-2">
          <p className="text-11 text-text-tertiary">本轮后端未返回维度评分，显示四项验收结果。</p>
          {view.legacyChecks.map((c) => (
            <div key={c.key} className="flex items-center justify-between rounded-md border border-border-subtle bg-bg-elevated px-2 py-1.5">
              <span className="text-12 text-text-secondary">{c.label}</span>
              <Chip tone={c.passed === true ? 'success' : c.passed === false ? 'error' : 'neutral'}>{c.passed === true ? '通过' : c.passed === false ? '未通过' : '未返回'}</Chip>
            </div>
          ))}
        </Panel>
      )}
    </Stage>
  );
}

function IssuesBlock({ view }: { view: CorrectorView }) {
  if (view.issues.length === 0) {
    const checked = view.totalChecks > 0 && view.passedCount === view.totalChecks;
    return (
      <Panel className="space-y-2">
        <p className="flex items-start gap-1.5 text-12 leading-relaxed text-text-primary">
          <BadgeCheck size={14} className="mt-0.5 shrink-0 text-status-success" />
          {checked ? '已按四项验收标准逐项检查，均达到要求，无需修改，原回答放行。' : '未发现需要修改的问题，原回答放行。'}
        </p>
        <div className="flex flex-wrap gap-1.5">
          <Chip tone="success">改动 0 处</Chip>
          <Chip tone="success">原文保留 100%</Chip>
          {view.structurePreserved !== false && <Chip tone="success">结构完整</Chip>}
        </div>
      </Panel>
    );
  }
  return (
    <ul className="space-y-1.5">
      {view.issues.map((issue, idx) => (
        <li key={issue.problem} className="t43-rise rounded-md border border-status-warning/30 bg-status-warning/5 p-2.5" style={delay(idx, 90, 300)}>
          <div className="flex flex-wrap items-center gap-1.5">
            {issue.dimensionLabel && <Chip tone="warning">{issue.dimensionLabel}</Chip>}
            <span className="text-12 font-medium leading-snug text-text-primary">{issue.problem}</span>
          </div>
          {issue.reason && <p className="mt-1 text-11 leading-relaxed text-text-secondary">原因：{issue.reason}</p>}
        </li>
      ))}
    </ul>
  );
}

function PatchStage({ view }: { view: CorrectorView }) {
  const patched = view.action === 'PATCH' || view.patches.length > 0;
  const ratio = view.changeRatio === null ? null : Math.round(view.changeRatio * 1000) / 10;
  return (
    <Stage index={2} title="定点修正" subtitle="发现了什么，怎么改" icon={PenLine} tone={patched ? 'warning' : 'success'}>
      <IssuesBlock view={view} />
      {view.patches.map((patch, idx) => (
        <Panel key={patch.before} className="t43-rise space-y-1.5" style={delay(idx, 120, 450)}>
          <div>
            <p className="text-11 text-status-error">修改前</p>
            <p className="rounded-sm bg-status-error/10 px-2 py-1 text-12 leading-relaxed text-text-secondary line-through decoration-status-error/50">{patch.before}</p>
          </div>
          <div className="flex justify-center text-text-tertiary">
            <ArrowDown size={14} className="t43-float" />
          </div>
          <div>
            <p className="text-11 text-status-success">修改后</p>
            <p className="t43-sweep rounded-sm bg-status-success/10 bg-gradient-to-r from-transparent via-status-success/25 to-transparent px-2 py-1 text-12 leading-relaxed text-text-primary" style={delay(idx, 120, 900)}>
              {patch.after}
            </p>
          </div>
          {patch.reason && <p className="text-11 leading-relaxed text-text-secondary">修改理由：{patch.reason}</p>}
        </Panel>
      ))}
      {patched && (
        <Panel className="grid grid-cols-3 gap-2">
          <Field label="修改处数">{view.patches.length} 处</Field>
          <Field label="改动比例">{ratio === null ? '—' : `约 ${ratio}%`}</Field>
          <Field label="原结构" tone={view.structurePreserved === false ? 'error' : 'success'}>
            {view.structurePreserved === null ? '—' : view.structurePreserved ? '保留' : '破坏'}
          </Field>
        </Panel>
      )}
    </Stage>
  );
}

function VerdictStage({ view }: { view: CorrectorView }) {
  const action = view.action;
  const delivered = action === 'PASS' || action === 'PATCH';
  return (
    <Stage index={3} title="质量自检" subtitle="验收结论" icon={ClipboardCheck} isLast tone={action ? ACTION_TONE[action] : 'neutral'}>
      {view.totalChecks > 0 && (
        <ul className="space-y-1.5">
          {view.legacyChecks.map((c, idx) => (
            <li key={c.key} className="t43-rise flex items-start gap-2 rounded-md border border-border-subtle bg-bg-base px-2.5 py-2" style={delay(idx, 110, 300)}>
              <span
                className={cn(
                  't43-pop mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-11',
                  c.passed === true ? 'bg-status-success/15 text-status-success' : c.passed === false ? 'bg-status-error/15 text-status-error' : 'bg-bg-elevated text-text-tertiary',
                )}
                style={delay(idx, 110, 450)}
              >
                {c.passed === true ? '✓' : c.passed === false ? '✕' : '·'}
              </span>
              <div className="min-w-0">
                <p className="text-12 font-medium text-text-primary">
                  {c.label}
                  <span className="ml-1.5 font-normal text-text-tertiary">{c.passed === true ? '通过' : c.passed === false ? '未通过' : ''}</span>
                </p>
                <p className="text-11 leading-relaxed text-text-tertiary">{c.criterion}</p>
              </div>
            </li>
          ))}
        </ul>
      )}
      <Panel className="grid grid-cols-2 gap-x-3 gap-y-2.5">
        <Field label="四项验收">{view.totalChecks > 0 ? `${view.passedCount}/${view.totalChecks} 通过` : '—'}</Field>
        <Field label="处理状态">{view.statusLabel || '—'}</Field>
        <Field label="问题严重程度">{view.severityLabel || (view.issues.length === 0 ? '无' : '—')}</Field>
        <Field label="重写次数">{view.regenerationCount} 次</Field>
        <Field label="带问题交付" tone={delivered && view.issues.length > 0 && action === 'PASS' ? 'warning' : undefined}>
          {action === '' ? '—' : delivered ? (action === 'PASS' && view.issues.length > 0 ? '是' : '否') : '否，已退回'}
        </Field>
        {view.requestedAction && view.requestedAction !== view.action && (
          <Field label="模型建议" tone="warning">{view.requestedAction}</Field>
        )}
      </Panel>
      {view.summary && (
        <p className="flex items-start gap-1.5 text-12 leading-relaxed text-text-secondary">
          <BadgeCheck size={14} className="mt-0.5 shrink-0 text-status-success" />
          {view.summary}
        </p>
      )}
    </Stage>
  );
}

/** 不带外壳的主体，可单独用于历史案例演示 */
export function ContentCorrectorView({ raw }: { raw: unknown }) {
  const view = useMemo(() => buildCorrectorView(raw), [raw]);
  const banner = bannerFor(view);
  return (
    <div>
      {banner && view.action && <ResultBanner icon={banner.icon} tone={banner.tone} label={`${view.action} · ${ACTION_LABEL[view.action]}`} title={banner.title} text={banner.text} />}
      <CorrectorMechanism action={view.action} />
      <EvaluationStage view={view} />
      <PatchStage view={view} />
      <VerdictStage view={view} />
    </div>
  );
}

interface FlowProps {
  onBack: () => void;
  onClose: () => void;
  output: Record<string, unknown> | null;
  isRunning: boolean;
}

export function ContentCorrectorFlow({ onBack, onClose, output, isRunning }: FlowProps) {
  return (
    <FlowShell icon={Sparkles} title="内容矫正" subtitle="CONTENT CORRECTOR TRACE" onBack={onBack} onClose={onClose}>
      {output ? <ContentCorrectorView raw={output} /> : <EmptyState running={isRunning} text="本轮暂未执行 / 无输出数据" />}
    </FlowShell>
  );
}

export default ContentCorrectorFlow;
