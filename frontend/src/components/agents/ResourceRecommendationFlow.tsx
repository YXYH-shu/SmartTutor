import { useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  ArrowRight,
  BookOpen,
  Check,
  ChevronLeft,
  Clock3,
  ExternalLink,
  FileQuestion,
  FileText,
  LayoutGrid,
  Lightbulb,
  Orbit,
  Play,
  Sparkles,
  Target,
  X,
  Zap,
  type LucideIcon,
} from 'lucide-react';
import type { RecommendedResource, ResourceRecommendationOutput } from '@/types';
import { cn } from '@/utils/cn';

interface Props {
  onBack: () => void;
  onClose: () => void;
  output: ResourceRecommendationOutput | null;
  message?: string;
  isRunning: boolean;
}

const TYPE_LABELS: Record<string, string> = {
  video: '视频',
  article: '文章',
  quiz: '测验',
  practice: '实践',
};

const DIFFICULTY_LABELS: Record<string, string> = {
  beginner: '入门',
  intermediate: '进阶',
  advanced: '挑战',
};

function typeIcon(type?: string): LucideIcon {
  if (type === 'video') return Play;
  if (type === 'quiz') return FileQuestion;
  if (type === 'practice') return Zap;
  return FileText;
}

function learningPosition(resource: RecommendedResource): { label: string; tone: string } {
  if (resource.type === 'quiz') return { label: '自测巩固', tone: 'text-violet-700 bg-violet-500/10 border-violet-400/20 dark:text-violet-300' };
  if (resource.type === 'practice') return { label: '动手实践', tone: 'text-cyan-700 bg-cyan-500/10 border-cyan-400/20 dark:text-cyan-300' };
  if (resource.difficulty === 'beginner') return { label: '打好基础', tone: 'text-emerald-700 bg-emerald-500/10 border-emerald-400/20 dark:text-emerald-300' };
  return { label: '拓展应用', tone: 'text-amber-700 bg-amber-500/10 border-amber-400/20 dark:text-amber-300' };
}

function learningTask(resource: RecommendedResource): string {
  if (resource.type === 'quiz') return '完成测验后，把错题涉及的概念记入学习清单。';
  if (resource.type === 'practice') return '边操作边记录现象，并用一句话解释背后的原理。';
  if (resource.type === 'article') return '阅读后提炼 3 条关键知识，再尝试讲给同学听。';
  return '观看时暂停两次，分别记录一个新概念和一个仍有疑问的地方。';
}

function recommendationReason(resource: RecommendedResource): string {
  const reason = resource.recommend_reason?.trim();
  if (reason && !['Selected by resource recall.', 'Based on similarity to the selected reference resource.'].includes(reason)) return reason;
  const focus = resource.knowledge_tags?.slice(0, 2).join('、');
  const prefix = focus ? `它聚焦“${focus}”，` : '它与本轮学习主题紧密相关，';
  if (resource.type === 'practice') return `${prefix}适合通过动手观察来验证刚学到的规律。`;
  if (resource.type === 'quiz') return `${prefix}适合在学习后检查理解，并发现还需要巩固的地方。`;
  if (resource.type === 'video' && resource.difficulty === 'beginner') return `${prefix}内容从基础讲起，适合先建立直观理解。`;
  if (resource.type === 'video') return `${prefix}通过视频联系具体场景，适合在掌握基础后继续拓展。`;
  return `${prefix}适合系统梳理知识，并加深对实际应用的理解。`;
}

function ResourceMotionStyles() {
  return (
    <style>{`
      @keyframes student-resource-enter { from { opacity: 0; transform: translateY(10px) scale(.985); } to { opacity: 1; transform: translateY(0) scale(1); } }
      @keyframes student-resource-drift { 0%,100% { transform: translate3d(0,0,0); opacity:.24; } 50% { transform: translate3d(10px,-8px,0); opacity:.52; } }
      @keyframes student-resource-orbit { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
      @keyframes student-resource-fill { from { width: 0%; } }
      @keyframes student-resource-pulse { 0%,100% { box-shadow: 0 0 0 0 rgba(52,211,153,.08); } 50% { box-shadow: 0 0 0 8px rgba(52,211,153,.03); } }
      .student-resource-enter { animation: student-resource-enter .46s cubic-bezier(.2,.8,.2,1) both; }
      .student-resource-drift { animation: student-resource-drift 5.5s ease-in-out infinite; }
      .student-resource-orbit { animation: student-resource-orbit 9s linear infinite; }
      .student-resource-fill { animation: student-resource-fill .9s cubic-bezier(.2,.8,.2,1) both; }
      .student-resource-pulse { animation: student-resource-pulse 2.2s ease-in-out infinite; }
      @media (prefers-reduced-motion: reduce) {
        .student-resource-enter,.student-resource-drift,.student-resource-orbit,.student-resource-fill,.student-resource-pulse { animation: none !important; }
      }
    `}</style>
  );
}

function Header({ onBack, onClose }: Pick<Props, 'onBack' | 'onClose'>) {
  return (
    <header className="relative z-20 flex h-14 items-center border-b border-border-subtle bg-bg-elevated/90 px-3 backdrop-blur-xl">
      <button onClick={onBack} className="flex h-8 w-8 items-center justify-center rounded-lg text-text-tertiary transition hover:bg-bg-base hover:text-text-primary" aria-label="返回智能体面板">
        <ChevronLeft size={17} />
      </button>
      <div className="ml-2 min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg border border-emerald-400/25 bg-emerald-500/10 text-emerald-600 dark:text-emerald-300"><BookOpen size={15} /></span>
          <div className="min-w-0">
            <h3 className="truncate text-[12px] font-semibold text-text-primary">我的资源学习方案</h3>
            <p className="font-mono text-[9px] uppercase tracking-[.16em] text-text-tertiary">Personal learning kit</p>
          </div>
        </div>
      </div>
      <button onClick={onClose} className="flex h-8 w-8 items-center justify-center rounded-lg text-text-tertiary transition hover:bg-bg-base hover:text-text-primary" aria-label="关闭详情"><X size={16} /></button>
    </header>
  );
}

function Hero({ message, resources }: { message: string; resources: RecommendedResource[] }) {
  const totalMinutes = resources.reduce((sum, item) => sum + (item.time_needed_min ?? 0), 0);
  const types = new Set(resources.map((item) => item.type).filter(Boolean)).size;
  const topics = new Set(resources.flatMap((item) => item.knowledge_tags ?? [])).size;
  return (
    <section className="student-resource-enter relative overflow-hidden rounded-xl border border-emerald-400/20 bg-[linear-gradient(135deg,rgba(16,185,129,.13),rgba(6,182,212,.05)_55%,transparent)] p-4 shadow-[0_16px_48px_rgba(16,185,129,.07)]">
      <span className="student-resource-drift absolute -right-10 -top-12 h-32 w-32 rounded-full bg-emerald-400/10 blur-2xl" />
      <span className="student-resource-drift absolute -bottom-10 left-10 h-24 w-24 rounded-full bg-cyan-400/10 blur-2xl [animation-delay:-2s]" />
      <div className="relative flex items-start gap-3">
        <div className="student-resource-pulse relative flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-emerald-400/30 bg-bg-elevated/75 text-emerald-600 dark:text-emerald-300">
          <BookOpen size={21} />
          <span className="student-resource-orbit absolute inset-1 rounded-lg border border-dashed border-emerald-400/25" />
        </div>
        <div className="min-w-0 flex-1">
          <span className="rounded-full border border-emerald-400/25 bg-emerald-500/10 px-2 py-0.5 font-mono text-[9px] uppercase tracking-wider text-emerald-700 dark:text-emerald-300">Ready to learn</span>
          <h4 className="mt-2 text-[14px] font-semibold tracking-tight text-text-primary">为你准备了 {resources.length} 个学习资源</h4>
          <p className="mt-1 line-clamp-2 text-[10px] leading-4 text-text-secondary">{message}</p>
        </div>
      </div>
      <div className="relative mt-4 grid grid-cols-3 gap-2">
        <HeroMetric label="预计用时" value={totalMinutes > 0 ? `${totalMinutes} 分钟` : '自主安排'} icon={Clock3} />
        <HeroMetric label="资源形式" value={`${types || resources.length} 种`} icon={LayoutGrid} />
        <HeroMetric label="覆盖主题" value={`${topics} 个`} icon={Target} accent />
      </div>
    </section>
  );
}


function HeroMetric({ label, value, icon: Icon, accent = false }: { label: string; value: string; icon: LucideIcon; accent?: boolean }) {
  return (
    <div className="rounded-lg border border-white/5 bg-bg-base/60 p-2 backdrop-blur-sm">
      <div className="flex items-center gap-1 text-[9px] text-text-tertiary"><Icon size={10} /><span className="truncate">{label}</span></div>
      <p className={cn('mt-1 truncate text-[12px] font-semibold', accent ? 'text-emerald-600 dark:text-emerald-300' : 'text-text-primary')}>{value}</p>
    </div>
  );
}

function TwoStagePath({ resourceCount }: { resourceCount: number }) {
  return (
    <section className="student-resource-enter rounded-xl border border-border-subtle bg-bg-elevated/65 p-3 [animation-delay:70ms]">
      <div className="flex items-center gap-2">
        <StageNode icon={Target} step="01" title="学习计划" subtitle="明确主题与学习节奏" active />
        <span className="h-px flex-1 bg-gradient-to-r from-emerald-400/50 to-cyan-400/30" />
        <StageNode icon={Sparkles} step="02" title="精选资源" subtitle={`${resourceCount} 项可直接开始`} active />
      </div>
    </section>
  );
}

function StageNode({ icon: Icon, step, title, subtitle, active }: { icon: LucideIcon; step: string; title: string; subtitle: string; active: boolean }) {
  return (
    <div className="flex min-w-0 flex-1 items-center gap-2">
      <span className={cn('flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border', active ? 'border-emerald-400/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-300' : 'border-border-subtle text-text-tertiary')}><Icon size={14} /></span>
      <div className="min-w-0"><p className="font-mono text-[8px] text-text-tertiary">STEP {step}</p><p className="truncate text-[10px] font-semibold text-text-primary">{title}</p><p className="truncate text-[8px] text-text-tertiary">{subtitle}</p></div>
    </div>
  );
}

function ResourceCard({ resource, index }: { resource: RecommendedResource; index: number }) {
  const Icon = typeIcon(resource.type);
  const position = learningPosition(resource);
  const rank = resource.rank ?? index + 1;
  return (
    <article className="student-resource-enter group relative overflow-hidden rounded-xl border border-border-subtle bg-bg-elevated/75 p-3 transition duration-300 hover:-translate-y-0.5 hover:border-emerald-400/35 hover:shadow-[0_12px_28px_rgba(16,185,129,.08)]" style={{ animationDelay: `${140 + index * 90}ms` }}>
      <span className="absolute right-0 top-0 h-20 w-20 rounded-bl-full bg-emerald-400/5" />
      <div className="relative flex gap-3">
        <div className="flex flex-col items-center gap-1.5">
          <span className={cn('flex h-9 w-9 items-center justify-center rounded-xl border font-mono text-[11px] font-semibold', rank === 1 ? 'border-amber-400/35 bg-amber-400/10 text-amber-700 dark:text-amber-300' : 'border-emerald-400/25 bg-emerald-500/8 text-emerald-700 dark:text-emerald-300')}>{rank}</span>
          <span className="text-[8px] text-text-tertiary">推荐</span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-start gap-2">
            <div className="min-w-0 flex-1"><span className={cn('inline-flex rounded-full border px-1.5 py-0.5 text-[8px]', position.tone)}>{position.label}</span><h5 className="mt-1.5 text-[11px] font-semibold leading-4 text-text-primary">{resource.title || '未命名资源'}</h5></div>
            {resource.url && <a href={resource.url} target="_blank" rel="noreferrer" className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-text-tertiary transition hover:bg-emerald-500/10 hover:text-emerald-600" aria-label="打开资源"><ExternalLink size={13} /></a>}
          </div>
          <div className="mt-2 flex flex-wrap gap-1">
            <Pill icon={Icon}>{TYPE_LABELS[resource.type || ''] || resource.type || '资源'}</Pill>
            {resource.difficulty && <Pill>{DIFFICULTY_LABELS[resource.difficulty] || resource.difficulty}</Pill>}
            {resource.time_needed_min !== undefined && <Pill icon={Clock3}>{resource.time_needed_min} 分钟</Pill>}
          </div>
          {resource.knowledge_tags && resource.knowledge_tags.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">{resource.knowledge_tags.slice(0, 3).map((tag) => <span key={tag} className="rounded-full border border-border-subtle bg-bg-base/70 px-1.5 py-0.5 text-[9px] text-text-secondary">{tag}</span>)}</div>
          )}
          <div className="mt-2 rounded-lg border border-amber-400/15 bg-amber-400/5 px-2 py-1.5">
            <div className="flex items-center gap-1 text-[9px] font-semibold text-amber-700 dark:text-amber-300"><Sparkles size={10} /><span>为什么推荐</span></div>
            <p className="mt-1 text-[9px] leading-4 text-text-secondary">{recommendationReason(resource)}</p>
          </div>
          <div className="mt-2 flex items-start gap-1.5 rounded-lg bg-emerald-500/5 px-2 py-1.5 text-[9px] leading-4 text-text-secondary"><Check size={10} className="mt-0.5 shrink-0 text-emerald-500" /><span>{learningTask(resource)}</span></div>
        </div>
      </div>
    </article>
  );
}

function Pill({ children, icon: Icon }: { children: ReactNode; icon?: LucideIcon }) {
  return <span className="inline-flex items-center gap-1 rounded-full bg-bg-base px-1.5 py-0.5 text-[9px] text-text-tertiary">{Icon && <Icon size={9} />}{children}</span>;
}

function LearningTips({ resources }: { resources: RecommendedResource[] }) {
  const beginner = resources.find((item) => item.difficulty === 'beginner');
  const quiz = resources.find((item) => item.type === 'quiz');
  return (
    <section className="student-resource-enter rounded-xl border border-amber-400/20 bg-[linear-gradient(135deg,rgba(251,191,36,.08),transparent)] p-3 [animation-delay:380ms]">
      <div className="flex items-start gap-2.5">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-amber-400/10 text-amber-600 dark:text-amber-300"><Lightbulb size={15} /></span>
        <div className="min-w-0"><h4 className="text-[10px] font-semibold text-text-primary">怎么开始更轻松？</h4><p className="mt-1 text-[9px] leading-4 text-text-secondary">{beginner ? `建议先学习《${beginner.title}》，建立基础后再进入拓展内容。` : '建议先从最熟悉的主题开始，再逐步挑战更复杂的内容。'}{quiz ? ' 最后用测验检查掌握情况。' : ''}</p></div>
      </div>
    </section>
  );
}

function WaitingState({ isRunning }: { isRunning: boolean }) {
  return (
    <div className="relative flex flex-1 flex-col items-center justify-center overflow-hidden p-6 text-center">
      <span className="student-resource-drift absolute h-44 w-44 rounded-full bg-emerald-400/10 blur-3xl" />
      <div className="student-resource-pulse relative flex h-20 w-20 items-center justify-center rounded-2xl border border-emerald-400/25 bg-emerald-500/8 text-emerald-600"><BookOpen size={30} /><span className="student-resource-orbit absolute inset-2 rounded-xl border border-dashed border-emerald-400/30" /></div>
      <h4 className="relative mt-5 text-[13px] font-semibold text-text-primary">{isRunning ? '正在准备学习资源' : '本轮暂无资源推荐'}</h4>
      <p className="relative mt-1 max-w-[220px] text-[10px] leading-4 text-text-tertiary">{isRunning ? '正在理解你的学习目标，并组合最合适的学习内容。' : '发送资源推荐请求后，这里会出现你的个性化学习方案。'}</p>
    </div>
  );
}

export function ResourceRecommendationFlow({ onBack, onClose, output, message, isRunning }: Props) {
  const [replayKey, setReplayKey] = useState(0);
  const resources = useMemo(() => (output?.resources ?? []).slice(0, 6), [output?.resources]);
  useEffect(() => { setReplayKey((value) => value + 1); }, [output]);
  return (
    <div className="absolute inset-0 z-30 flex flex-col overflow-hidden bg-bg-base">
      <ResourceMotionStyles />
      <Header onBack={onBack} onClose={onClose} />
      <div key={replayKey} className="min-h-0 flex-1 overflow-y-auto px-3 pb-6 pt-3 [scrollbar-width:thin]">
        {output ? <div className="space-y-3"><Hero message={message || '本轮资源推荐请求'} resources={resources} /><TwoStagePath resourceCount={resources.length} /><div className="flex items-center justify-between px-0.5"><h4 className="text-[11px] font-semibold text-text-primary">精选资源</h4><span className="text-[9px] text-text-tertiary">按推荐顺序查看</span></div><div className="space-y-2">{resources.map((resource, index) => <ResourceCard key={`${resource.id}-${index}`} resource={resource} index={index} />)}</div><LearningTips resources={resources} /></div> : <WaitingState isRunning={isRunning} />}
      </div>
    </div>
  );
}

export default ResourceRecommendationFlow;
