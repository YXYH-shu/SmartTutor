/**
 * 4.3 可视化共用元件（按 320px 右栏设计）：抽屉外壳、步骤卡片、结果横幅、标签。
 * 只使用项目已有的设计 token。动效见 motion.tsx。
 */
import type { ReactNode } from 'react';
import { ChevronLeft, X, type LucideIcon } from 'lucide-react';
import { cn } from '@/utils/cn';
import { delay, MotionStyles } from './motion';

export type Tone = 'neutral' | 'accent' | 'success' | 'warning' | 'error' | 'info';

export const TONE_CHIP: Record<Tone, string> = {
  neutral: 'border-border-subtle bg-bg-base text-text-secondary',
  accent: 'border-accent/40 bg-accent-soft text-accent',
  success: 'border-status-success/40 bg-status-success/10 text-status-success',
  warning: 'border-status-warning/40 bg-status-warning/10 text-status-warning',
  error: 'border-status-error/40 bg-status-error/10 text-status-error',
  info: 'border-status-info/40 bg-status-info/10 text-status-info',
};

export const TONE_TEXT: Record<Tone, string> = {
  neutral: 'text-text-secondary',
  accent: 'text-accent',
  success: 'text-status-success',
  warning: 'text-status-warning',
  error: 'text-status-error',
  info: 'text-status-info',
};

export const TONE_BAR: Record<Tone, string> = {
  neutral: 'bg-text-tertiary',
  accent: 'bg-accent',
  success: 'bg-status-success',
  warning: 'bg-status-warning',
  error: 'bg-status-error',
  info: 'bg-status-info',
};

export function Chip({ tone = 'neutral', icon: Icon, children, className }: { tone?: Tone; icon?: LucideIcon; children: ReactNode; className?: string }) {
  return (
    <span className={cn('inline-flex items-center gap-1 rounded-sm border px-1.5 py-0.5 text-11', TONE_CHIP[tone], className)}>
      {Icon && <Icon size={11} strokeWidth={2} />}
      {children}
    </span>
  );
}

/** 小标题 + 值 */
export function Field({ label, children, tone }: { label: string; children: ReactNode; tone?: Tone }) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <span className="text-11 text-text-tertiary">{label}</span>
      <span className={cn('break-words text-12 font-medium', tone ? TONE_TEXT[tone] : 'text-text-primary')}>{children}</span>
    </div>
  );
}

export function Panel({ children, className, style }: { children: ReactNode; className?: string; style?: React.CSSProperties }) {
  return (
    <div style={style} className={cn('rounded-md border border-border-subtle bg-bg-base p-2.5 transition-colors duration-200 hover:border-border-strong', className)}>
      {children}
    </div>
  );
}

export interface FieldItem {
  label: string;
  /** null / undefined / '' 表示后端没有这项数据，整项不显示 */
  value: ReactNode | null | undefined;
  tone?: Tone;
  wide?: boolean;
}

/** 只渲染有数据的字段，避免大片“未返回” */
export function FieldGrid({ items, className }: { items: FieldItem[]; className?: string }) {
  const shown = items.filter((i) => i.value !== null && i.value !== undefined && i.value !== '');
  if (shown.length === 0) return null;
  return (
    <Panel className={cn('grid grid-cols-2 gap-x-3 gap-y-2.5', className)}>
      {shown.map((i) => (
        <div key={i.label} className={i.wide ? 'col-span-2' : undefined}>
          <Field label={i.label} tone={i.tone}>
            {i.value}
          </Field>
        </div>
      ))}
    </Panel>
  );
}

interface StageProps {
  index: number;
  title: string;
  subtitle?: string;
  icon: LucideIcon;
  /** active 正常展示；muted 表示本轮未触发（灰显并折叠说明） */
  state?: 'active' | 'muted';
  tone?: Tone;
  isLast?: boolean;
  mutedHint?: string;
  children?: ReactNode;
}

/** 左侧图标圆点 + 竖线连接的步骤卡片，对应演示讲解词的一个镜头。第 index 项依次入场。 */
export function Stage({ index, title, subtitle, icon: Icon, state = 'active', tone = 'accent', isLast, mutedHint, children }: StageProps) {
  const muted = state === 'muted';
  const d = delay(index, 110, 120);
  return (
    <section className="relative flex gap-2.5" aria-label={title}>
      <div className="relative flex w-7 shrink-0 flex-col items-center">
        <div className="relative z-10">
          {!muted && <span className={cn('t43-ping absolute inset-0 rounded-full border', TONE_CHIP[tone])} style={d} />}
          <div
            className={cn(
              't43-pop relative flex h-7 w-7 items-center justify-center rounded-full border',
              muted ? 'border-border-subtle bg-bg-base text-text-tertiary' : cn('bg-bg-elevated', TONE_CHIP[tone]),
            )}
            style={d}
          >
            <Icon size={14} strokeWidth={1.75} />
          </div>
        </div>
        {!isLast && <div className="t43-line mt-1 w-px flex-1 bg-border-subtle" style={d} />}
      </div>
      <div className={cn('t43-rise min-w-0 flex-1', isLast ? 'pb-1' : 'pb-5')} style={d}>
        <div className="flex flex-wrap items-baseline gap-x-1.5">
          <span className="font-mono text-11 text-text-tertiary">{String(index).padStart(2, '0')}</span>
          <h4 className={cn('text-14 font-display font-semibold', muted ? 'text-text-tertiary' : 'text-text-primary')}>{title}</h4>
        </div>
        {subtitle && <p className="text-11 leading-snug text-text-tertiary">{subtitle}</p>}
        {muted ? (
          <p className="mt-1.5 text-12 text-text-tertiary">{mutedHint ?? '本轮未触发'}</p>
        ) : (
          <div className="mt-2 space-y-2">{children}</div>
        )}
      </div>
    </section>
  );
}

/** 顶部结果横幅：一句话结论 + 图标光环，状态一目了然 */
export function ResultBanner({ icon: Icon, tone, label, title, text }: { icon: LucideIcon; tone: Tone; label: string; title: string; text: string }) {
  return (
    <div className={cn('t43-rise t43-glow mb-4 flex items-start gap-2.5 rounded-lg border p-3', TONE_CHIP[tone])}>
      <div className="relative mt-0.5 shrink-0">
        <span className="t43-ping absolute inset-0 rounded-full bg-current opacity-30" />
        <div className="t43-float relative flex h-8 w-8 items-center justify-center rounded-full border border-current/40 bg-bg-elevated">
          <Icon size={16} strokeWidth={1.9} />
        </div>
      </div>
      <div className="min-w-0">
        <p className="font-mono text-11 opacity-80">{label}</p>
        <p className="text-14 font-display font-semibold text-text-primary">{title}</p>
        <p className="mt-0.5 text-12 leading-relaxed text-text-secondary">{text}</p>
      </div>
    </div>
  );
}

interface ShellProps {
  icon: LucideIcon;
  title: string;
  subtitle: string;
  onBack: () => void;
  onClose: () => void;
  children: ReactNode;
}

/** 抽屉外壳：头部与 StudyBuddyFlow / ResourceRecommendationFlow 保持一致（状态芯片移到正文横幅） */
export function FlowShell({ icon: Icon, title, subtitle, onBack, onClose, children }: ShellProps) {
  return (
    <div className="absolute inset-0 z-30 flex flex-col bg-bg-elevated animate-slide-in-right">
      <MotionStyles />
      <div className="flex items-center justify-between border-b border-border-subtle px-3 py-3">
        <div className="flex min-w-0 items-center gap-2">
          <button
            type="button"
            onClick={onBack}
            className="shrink-0 rounded-md p-1.5 text-text-tertiary transition-colors hover:bg-bg-base hover:text-text-primary"
            title="返回智能体面板"
            aria-label="返回智能体面板"
          >
            <ChevronLeft size={16} />
          </button>
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-accent/30 bg-accent-soft text-accent">
            <Icon size={16} />
          </div>
          <div className="min-w-0">
            <h3 className="truncate text-16 font-display font-semibold text-text-primary">{title}</h3>
            <p className="truncate font-mono text-11 text-text-tertiary">{subtitle}</p>
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="shrink-0 rounded-md p-1.5 text-text-tertiary transition-colors hover:bg-bg-base hover:text-text-primary"
          title="关闭详情"
          aria-label="关闭详情"
        >
          <X size={16} />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-3 py-4 scrollbar-thin">{children}</div>
    </div>
  );
}

/** 暂无数据占位 */
export function EmptyState({ running, text }: { running: boolean; text: string }) {
  return (
    <div className="flex h-40 items-center justify-center rounded-md border border-dashed border-border-subtle text-12 text-text-tertiary">
      {running ? '智能体运行中，等待输出…' : text}
    </div>
  );
}
