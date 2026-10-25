/**
 * 安全监测可视化：风险感知 → 意图识别 → 价值评估 → 教育引导 → 问题转化（按 320px 右栏设计）。
 *
 * - SafetyMonitorView：只依赖原始 trace，可脱离 store / API 单独使用（历史案例演示）。
 * - SafetyMonitorFlow：套上抽屉外壳，供 AgentDetailDrawer 使用。
 */
import { useMemo } from 'react';
import {
  Atom,
  Ban,
  BookOpen,
  Check,
  Compass,
  Crosshair,
  Dna,
  FlaskConical,
  Globe,
  GraduationCap,
  Heart,
  Landmark,
  Radar,
  Scale,
  Search,
  Shield,
  ShieldAlert,
  ShieldCheck,
  TriangleAlert,
  Wand2,
  type LucideIcon,
} from 'lucide-react';
import { cn } from '@/utils/cn';
import { delay } from './motion';
import { SafetyMechanism } from './MechanismFlow';
import { buildSafetyView, INTENT_LABELS } from './safetyAdapter';
import { Chip, EmptyState, FieldGrid, FlowShell, Panel, ResultBanner, Stage, type Tone } from './primitives';
import type { SafetyBranch, SafetyIntent, SafetyView } from './types';

const BRANCH_TONE: Record<SafetyBranch, Tone> = { PASS: 'success', REJECT: 'error', GUIDE: 'accent' };
const BRANCH_ICON: Record<SafetyBranch, LucideIcon> = { PASS: ShieldCheck, REJECT: Ban, GUIDE: Compass };
const INTENT_ICON: Record<SafetyIntent, LucideIcon> = { learning: BookOpen, emotional: Heart, probing: Search, malicious: ShieldAlert };

function categoryTone(category: string): Tone {
  if (category === 'N' || category === '') return 'success';
  if (category === 'C') return 'error';
  return 'warning';
}

/** 布尔值转文字；没有数据返回 null，交给 FieldGrid 隐藏 */
function yesNo(value: boolean | null): string | null {
  return value === true ? '是' : value === false ? '否' : null;
}

function subjectIcon(key: string, label: string): LucideIcon {
  const text = `${key} ${label}`;
  if (/physic|物理/i.test(text)) return Atom;
  if (/biolog|生物/i.test(text)) return Dna;
  if (/chem|化学/i.test(text)) return FlaskConical;
  if (/geo|地理/i.test(text)) return Globe;
  if (/moral|ethic|law|道德|法治/i.test(text)) return Landmark;
  return BookOpen;
}

/** 顶部结论：只用 trace 里已有的字段拼一句话，不编造 */
function bannerFor(view: SafetyView): { icon: LucideIcon; tone: Tone; text: string } | null {
  if (!view.branch) return null;
  const { perception: p, transform: t, selectionText } = view;
  const topic = p.coreTopic || p.originalQuery;
  if (view.branch === 'REJECT') {
    return { icon: Ban, tone: 'error', text: `该请求不进入教学，系统直接给出安全回应${p.categoryLabel ? `（${p.categoryLabel}）` : ''}。` };
  }
  if (view.branch === 'GUIDE') {
    if (view.mode === 'classified') {
      return { icon: Compass, tone: 'accent', text: `保留“${topic}”的科学主题，剥离危险操作，转成学习任务引导学生选择。` };
    }
    return { icon: Compass, tone: 'accent', text: `学生选了“${selectionText}”，继续引导确定具体知识点。` };
  }
  if (view.mode === 'focus_chosen') {
    return { icon: ShieldCheck, tone: 'success', text: `学生确认学习“${selectionText}”，引导完成，带着安全约束进入教学。` };
  }
  return { icon: ShieldCheck, tone: 'success', text: t.triggered ? `已转化为安全学习目标，进入教学。` : '未发现风险，直接进入学习。' };
}

function SeverityMeter({ level, label }: { level: string; label: string }) {
  const filled = ({ low: 1, moderate: 2, high: 3, severe: 4 } as Record<string, number>)[level] ?? 0;
  if (filled === 0) return null;
  const color = filled >= 3 ? 'bg-status-error' : 'bg-status-warning';
  return (
    <div className="flex items-center gap-2">
      <span className="shrink-0 text-11 text-text-tertiary">危害程度</span>
      <div className="flex flex-1 gap-1">
        {[0, 1, 2, 3].map((i) => (
          <span key={i} className={cn('h-1.5 flex-1 rounded-full', i < filled ? cn('t43-seg', color) : 'bg-bg-elevated')} style={delay(i, 120, 400)} />
        ))}
      </div>
      <span className="shrink-0 text-11 text-text-secondary">{label}</span>
    </div>
  );
}

function PerceptionStage({ view }: { view: SafetyView }) {
  const p = view.perception;
  const risky = p.category !== '' && p.category !== 'N';
  return (
    <Stage index={1} title="风险感知" subtitle="感知到什么风险" icon={Radar} tone={categoryTone(p.category)}>
      {p.originalQuery && (
        <Panel>
          <p className="text-11 text-text-tertiary">学生提问</p>
          <p className="mt-0.5 text-14 font-medium leading-snug text-text-primary">“{p.originalQuery}”</p>
        </Panel>
      )}
      {p.category && (
        <div className="flex flex-wrap items-center gap-1.5">
          <Chip tone={categoryTone(p.category)} icon={risky ? TriangleAlert : ShieldCheck}>
            风险类别 {p.category}
          </Chip>
          {p.categoryLabel && <Chip tone="neutral">{p.categoryLabel}</Chip>}
        </div>
      )}
      {risky && <SeverityMeter level={p.severity} label={p.severityLabel} />}
      <FieldGrid
        items={[
          { label: '检测到风险', value: p.riskDetected === null ? (p.category ? (risky ? '是' : '否') : null) : yesNo(p.riskDetected), tone: risky ? 'warning' : 'success' },
          { label: '判断置信度', value: p.confidence === null ? null : `${Math.round(p.confidence * 100)}%` },
          { label: '核心主题', value: p.coreTopic, wide: true },
        ]}
      />
      {view.mode !== 'classified' && (
        <p className="rounded-md border border-border-subtle bg-bg-base px-2.5 py-2 text-12 leading-relaxed text-text-secondary">
          本轮是点选系统给的选项，不是新的自由提问，不重新做风险分类，沿用首轮对“{p.coreTopic || p.originalQuery || '该主题'}”的判断。
        </p>
      )}
    </Stage>
  );
}

function IntentStage({ view }: { view: SafetyView }) {
  const i = view.intent;
  const order: SafetyIntent[] = ['learning', 'emotional', 'probing', 'malicious'];
  return (
    <Stage index={2} title="意图识别" subtitle="识别到什么意图" icon={Crosshair}>
      <div className="grid grid-cols-2 gap-1.5">
        {order.map((key, idx) => {
          const active = view.mode === 'classified' ? i.intent === key : key === 'learning';
          const tone: Tone = key === 'malicious' ? 'error' : key === 'probing' ? 'warning' : 'accent';
          const Icon = INTENT_ICON[key];
          return (
            <div
              key={key}
              className={cn(
                't43-rise flex items-center gap-1.5 rounded-md border px-2 py-1.5 text-12 transition-colors',
                active ? cn('font-medium', tone === 'error' ? 'border-status-error/50 bg-status-error/10 text-status-error' : tone === 'warning' ? 'border-status-warning/50 bg-status-warning/10 text-status-warning' : 'border-accent/40 bg-accent-soft text-accent') : 'border-border-subtle bg-bg-base text-text-tertiary',
              )}
              style={delay(idx, 70, 300)}
            >
              <Icon size={13} strokeWidth={1.75} />
              {INTENT_LABELS[key]}
              {active && <Check size={12} className="ml-auto" />}
            </div>
          );
        })}
      </div>
      {view.mode === 'classified' ? (
        <FieldGrid
          items={[
            { label: '请求类型', value: i.requestTypeLabel, wide: true },
            { label: '操作性请求', value: yesNo(i.operationalRequest), tone: i.operationalRequest ? 'warning' : undefined },
            { label: '重复试探', value: yesNo(i.repeatProbe) },
            { label: '危机信号', value: yesNo(i.crisisDetected), tone: i.crisisDetected ? 'error' : undefined },
          ]}
        />
      ) : (
        <Panel className="space-y-1">
          <p className="text-11 text-text-tertiary">{view.mode === 'subject_chosen' ? '学生选择的学科视角' : '学生选择的知识焦点'}</p>
          <p className="text-14 font-medium leading-snug text-text-primary">{view.selectionText || '（选项文本未返回）'}</p>
          <p className="text-11 leading-relaxed text-text-tertiary">点选系统给出的选项视为明确的学习意图，由规则直接匹配，不经过模型判断。</p>
        </Panel>
      )}
    </Stage>
  );
}

function BranchRow({ active }: { active: SafetyBranch | '' }) {
  const items: Array<{ id: SafetyBranch; label: string }> = [
    { id: 'PASS', label: '进入学习' },
    { id: 'REJECT', label: '安全回应' },
    { id: 'GUIDE', label: '教育引导' },
  ];
  return (
    <div className="grid grid-cols-3 gap-1.5">
      {items.map(({ id, label }, idx) => {
        const on = active === id;
        const Icon = BRANCH_ICON[id];
        const tone = BRANCH_TONE[id];
        return (
          <div
            key={id}
            style={delay(idx, 80, 300)}
            className={cn(
              't43-rise flex flex-col items-center gap-0.5 rounded-md border px-1 py-1.5 text-11 transition-colors',
              on ? cn('font-medium', tone === 'error' ? 'border-status-error/50 bg-status-error/10 text-status-error' : tone === 'success' ? 'border-status-success/50 bg-status-success/10 text-status-success' : 'border-accent/40 bg-accent-soft text-accent') : 'border-border-subtle bg-bg-base text-text-tertiary',
            )}
          >
            <Icon size={14} strokeWidth={1.75} />
            {label}
          </div>
        );
      })}
    </div>
  );
}

function ListFold({ title, items, tone }: { title: string; items: string[]; tone: Tone }) {
  if (items.length === 0) return null;
  return (
    <details className="group rounded-md border border-border-subtle bg-bg-base px-2.5 py-2">
      <summary className="flex cursor-pointer select-none list-none items-center gap-1.5 text-12 text-text-secondary">
        <span className={cn('h-1.5 w-1.5 rounded-full', tone === 'success' ? 'bg-status-success' : 'bg-status-error')} />
        {title}
        <span className="ml-auto text-11 text-text-tertiary">{items.length} 条 ▾</span>
      </summary>
      <ul className="mt-2 list-disc space-y-1 pl-4 text-11 leading-relaxed text-text-tertiary">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </details>
  );
}

function ValueStage({ view }: { view: SafetyView }) {
  const v = view.value;
  const riskFree = view.perception.category === 'N';
  const classified = view.mode === 'classified';
  const choiceBasis =
    view.mode === 'subject_chosen'
      ? '学生已选定学科，继续引导选择该学科内的具体知识点'
      : view.mode === 'focus_chosen'
        ? '学生已确认知识焦点，引导完成，携带安全约束进入教学'
        : '';
  return (
    <Stage index={3} title="价值评估" subtitle="如何评估教育转化价值" icon={Scale}>
      <BranchRow active={v.branch} />
      <FieldGrid
        items={[
          { label: '可转化为教学', value: classified ? (riskFree ? '无需转化' : yesNo(v.teachable)) : null, tone: v.teachable && !riskFree ? 'success' : undefined },
          { label: '判断来源', value: classified ? v.decisionSourceLabel : '选项匹配（规则）' },
          { label: '处理依据', value: classified ? v.policyLabel : choiceBasis, wide: true },
          { label: '拒绝类型', value: v.branch === 'REJECT' ? v.rejectType || '未标注类型' : null, tone: 'error', wide: true },
        ]}
      />
      <ListFold title="可保留的教学内容" items={v.allowed} tone="success" />
      <ListFold title="不提供的内容" items={v.forbidden} tone="error" />
    </Stage>
  );
}

function GuidanceStage({ view }: { view: SafetyView }) {
  const g = view.guidance;
  return (
    <Stage
      index={4}
      title="教育引导"
      subtitle="引导学生选择学习方向"
      icon={Compass}
      state={g.triggered ? 'active' : 'muted'}
      mutedHint={view.branch === 'REJECT' ? '本轮直接安全回应，不进入教育引导' : '本轮无需引导，直接进入学习'}
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <Chip tone="accent" icon={Compass}>{g.phase === 'focus' ? '第二步：选知识焦点' : '第一步：选学科视角'}</Chip>
        {g.fallback && <Chip tone="warning" icon={TriangleAlert}>兜底生成</Chip>}
      </div>
      {g.coreTopic && (
        <Panel>
          <p className="text-11 text-text-tertiary">保留的科学主题</p>
          <p className="mt-0.5 text-14 font-medium text-text-primary">{g.coreTopic}</p>
        </Panel>
      )}
      {g.phase === 'subject' && (
        <ol className="space-y-1.5">
          {g.subjects.map((s, idx) => {
            const Icon = subjectIcon(s.key, s.label);
            const recommended = s.label === g.recommendedOption || (idx === 0 && !g.recommendedOption);
            return (
              <li key={s.key} className="t43-rise rounded-md border border-border-subtle bg-bg-base p-2.5 transition-colors hover:border-accent/40" style={delay(idx, 100, 350)}>
                <div className="flex items-center gap-2">
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-accent-soft text-accent">
                    <Icon size={14} strokeWidth={1.75} />
                  </span>
                  <span className="min-w-0 flex-1 text-12 font-medium leading-snug text-text-primary">{s.label}</span>
                  {recommended && <Chip tone="accent">推荐</Chip>}
                </div>
                {s.focus && <p className="mt-1.5 text-11 leading-relaxed text-text-tertiary">可探究：{s.focus}</p>}
              </li>
            );
          })}
        </ol>
      )}
      {g.phase === 'focus' && (
        <>
          {g.selectedSubjectLabel && (
            <p className="flex items-start gap-1.5 text-12 leading-relaxed text-text-secondary">
              <Check size={13} className="mt-0.5 shrink-0 text-status-success" />
              已选学科：<span className="font-medium text-text-primary">{g.selectedSubjectLabel}</span>
            </p>
          )}
          <ol className="space-y-1.5">
            {g.focusOptions.map((option, idx) => (
              <li key={option} className="t43-rise flex items-start gap-2 rounded-md border border-border-subtle bg-bg-base p-2.5 transition-colors hover:border-accent/40" style={delay(idx, 100, 350)}>
                <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-accent-soft font-mono text-11 text-accent">{idx + 1}</span>
                <span className="min-w-0 flex-1 text-12 leading-snug text-text-primary">{option}</span>
                {option === g.recommendedOption && <Chip tone="accent">推荐</Chip>}
              </li>
            ))}
          </ol>
        </>
      )}
    </Stage>
  );
}

function TransformStage({ view }: { view: SafetyView }) {
  const t = view.transform;
  return (
    <Stage index={5} title="问题转化" subtitle="总结为安全的学习任务" icon={Wand2} isLast state={t.triggered ? 'active' : 'muted'} mutedHint="本轮没有需要转化的风险问题">
      <Panel className="space-y-2">
        {t.originalQuery && (
          <div>
            <p className="text-11 text-text-tertiary">原始提问</p>
            <p className="text-12 leading-snug text-text-tertiary line-through decoration-status-error/60">{t.originalQuery}</p>
          </div>
        )}
        <div className="flex items-center gap-2 text-accent">
          <span className="h-px flex-1 bg-gradient-to-r from-transparent via-accent/50 to-accent/50" />
          <Wand2 size={13} className="t43-float" />
          <span className="h-px flex-1 bg-gradient-to-l from-transparent via-accent/50 to-accent/50" />
        </div>
        <div className="t43-blur-in" style={delay(0, 0, 600)}>
          <p className="text-11 text-accent">转化后的学习目标</p>
          <p className="text-14 font-medium leading-snug text-text-primary">{t.safeGoal}</p>
        </div>
      </Panel>
      {t.constraints.length > 0 && (
        <ul className="space-y-1">
          {t.constraints.map((c, idx) => (
            <li key={c} className="t43-rise flex items-start gap-1.5 text-11 leading-relaxed text-text-secondary" style={delay(idx, 90, 700)}>
              <Check size={12} className="mt-0.5 shrink-0 text-status-success" />
              {c}
            </li>
          ))}
        </ul>
      )}
    </Stage>
  );
}

/** 不带外壳的主体，可单独用于历史案例演示 */
export function SafetyMonitorView({ raw }: { raw: unknown }) {
  const view = useMemo(() => buildSafetyView(raw), [raw]);
  const banner = bannerFor(view);
  return (
    <div>
      {banner && view.branch && (
        <ResultBanner icon={banner.icon} tone={banner.tone} label={`${view.branch} · ${view.branchLabel}`} title={view.mode === 'classified' ? '安全监测结论' : '引导进度'} text={banner.text} />
      )}
      <SafetyMechanism branch={view.branch} mode={view.mode} />
      <PerceptionStage view={view} />
      <IntentStage view={view} />
      <ValueStage view={view} />
      <GuidanceStage view={view} />
      <TransformStage view={view} />
    </div>
  );
}

interface FlowProps {
  onBack: () => void;
  onClose: () => void;
  output: Record<string, unknown> | null;
  isRunning: boolean;
}

export function SafetyMonitorFlow({ onBack, onClose, output, isRunning }: FlowProps) {
  return (
    <FlowShell icon={Shield} title="安全监测" subtitle="SAFETY MONITOR TRACE" onBack={onBack} onClose={onClose}>
      {output ? <SafetyMonitorView raw={output} /> : <EmptyState running={isRunning} text="本轮暂未执行 / 无输出数据" />}
    </FlowShell>
  );
}

export default SafetyMonitorFlow;
