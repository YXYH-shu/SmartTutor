import { useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  BookOpenCheck,
  Check,
  ChevronLeft,
  Clock3,
  HeartHandshake,
  Lightbulb,
  MessageCircle,
  ShieldCheck,
  Sparkles,
  Target,
  UserRound,
  Users,
  X,
  type LucideIcon,
} from 'lucide-react';
import type { RecommendedBuddy, StudyBuddyOutput } from '@/types';
import { cn } from '@/utils/cn';

interface Props {
  onBack: () => void;
  onClose: () => void;
  output: StudyBuddyOutput | null;
  message?: string;
  isRunning: boolean;
}

const TOPIC_LABELS: Record<string, string> = {
  field: '电场与电荷',
  'voltage-current': '电压与电流',
  safety: '用电安全',
  circuit: '电路基础',
  emergency: '应急处理',
  insulation: '绝缘防护',
  ethics: '技术伦理',
  media: '信息辨识',
  animal: '生态与动物',
  power: '电功率',
  grid: '输电系统',
};

function topicLabel(raw: string): string {
  const key = raw.replace(/^kp-elec-/, '');
  return TOPIC_LABELS[key] || key.replace(/-/g, ' ');
}

function roleFor(buddy: RecommendedBuddy): { title: string; description: string; tone: string } {
  const joined = (buddy.strengths ?? []).join(' ');
  if (/emergency|safety|insulation/.test(joined)) return { title: '安全实践搭档', description: '适合一起讨论安全边界和实际应用', tone: 'text-amber-700 bg-amber-500/10 border-amber-400/20 dark:text-amber-300' };
  if (/media|ethics|animal/.test(joined)) return { title: '跨学科讨论搭档', description: '适合拓展电学与生活、社会的联系', tone: 'text-violet-700 bg-violet-500/10 border-violet-400/20 dark:text-violet-300' };
  return { title: '基础概念搭档', description: '适合互相讲解概念和梳理电路知识', tone: 'text-cyan-700 bg-cyan-500/10 border-cyan-400/20 dark:text-cyan-300' };
}

function buddyReason(buddy: RecommendedBuddy): string {
  if (buddy.recommend_reason?.trim()) return buddy.recommend_reason.trim();
  const topics = (buddy.strengths ?? []).slice(0, 2).map(topicLabel);
  const mode = buddy.collaboration_mode || '互问互答';
  return topics.length > 0
    ? `这位学伴熟悉“${topics.join('、')}”，适合通过${mode}帮助你补充思路、检查理解。`
    : `这位学伴适合与你通过${mode}梳理本轮知识，并交流不同的解题思路。`;
}

function BuddyMotionStyles() {
  return (
    <style>{`
      @keyframes student-buddy-enter { from { opacity:0; transform:translateY(10px) scale(.985); } to { opacity:1; transform:translateY(0) scale(1); } }
      @keyframes student-buddy-orbit { from { transform:rotate(0deg); } to { transform:rotate(360deg); } }
      @keyframes student-buddy-radar { 0% { transform:scale(.45); opacity:.7; } 100% { transform:scale(1.35); opacity:0; } }
      @keyframes student-buddy-drift { 0%,100% { transform:translate3d(0,0,0); opacity:.24; } 50% { transform:translate3d(-8px,10px,0); opacity:.5; } }
      @keyframes student-buddy-pulse { 0%,100% { box-shadow:0 0 0 0 rgba(34,211,238,.1); } 50% { box-shadow:0 0 0 7px rgba(34,211,238,.035); } }
      .student-buddy-enter { animation:student-buddy-enter .46s cubic-bezier(.2,.8,.2,1) both; }
      .student-buddy-orbit { animation:student-buddy-orbit 9s linear infinite; }
      .student-buddy-radar { animation:student-buddy-radar 2.4s ease-out infinite; }
      .student-buddy-drift { animation:student-buddy-drift 5.8s ease-in-out infinite; }
      .student-buddy-pulse { animation:student-buddy-pulse 2.1s ease-in-out infinite; }
      @media (prefers-reduced-motion:reduce) { .student-buddy-enter,.student-buddy-orbit,.student-buddy-radar,.student-buddy-drift,.student-buddy-pulse { animation:none!important; } }
    `}</style>
  );
}

function Header({ onBack, onClose }: Pick<Props, 'onBack' | 'onClose'>) {
  return (
    <header className="relative z-20 flex h-14 items-center border-b border-border-subtle bg-bg-elevated/90 px-3 backdrop-blur-xl">
      <button onClick={onBack} className="flex h-8 w-8 items-center justify-center rounded-lg text-text-tertiary transition hover:bg-bg-base hover:text-text-primary" aria-label="返回智能体面板"><ChevronLeft size={17} /></button>
      <div className="ml-2 min-w-0 flex-1"><div className="flex items-center gap-2"><span className="flex h-7 w-7 items-center justify-center rounded-lg border border-cyan-400/25 bg-cyan-500/10 text-cyan-600 dark:text-cyan-300"><Users size={15} /></span><div className="min-w-0"><h3 className="truncate text-[12px] font-semibold text-text-primary">我的学习小组</h3><p className="font-mono text-[9px] uppercase tracking-[.16em] text-text-tertiary">Study together</p></div></div></div>
      <button onClick={onClose} className="flex h-8 w-8 items-center justify-center rounded-lg text-text-tertiary transition hover:bg-bg-base hover:text-text-primary" aria-label="关闭详情"><X size={16} /></button>
    </header>
  );
}

function Hero({ message, buddies }: { message: string; buddies: RecommendedBuddy[] }) {
  const modes = new Set(buddies.map((item) => item.collaboration_mode).filter(Boolean)).size;
  const topics = new Set(buddies.flatMap((item) => item.strengths ?? [])).size;
  return (
    <section className="student-buddy-enter relative overflow-hidden rounded-xl border border-cyan-400/20 bg-[linear-gradient(135deg,rgba(6,182,212,.13),rgba(99,102,241,.06)_58%,transparent)] p-4 shadow-[0_16px_48px_rgba(6,182,212,.07)]">
      <span className="student-buddy-drift absolute -right-12 -top-14 h-36 w-36 rounded-full bg-cyan-400/10 blur-2xl" /><span className="student-buddy-drift absolute -bottom-12 left-8 h-28 w-28 rounded-full bg-indigo-400/10 blur-2xl [animation-delay:-2s]" />
      <div className="relative flex items-start gap-3">
        <div className="relative flex h-14 w-14 shrink-0 items-center justify-center rounded-full border border-cyan-400/30 bg-bg-elevated/70 text-cyan-600 dark:text-cyan-300"><Users size={22} /><span className="student-buddy-radar absolute inset-0 rounded-full border border-cyan-400/30" /><span className="student-buddy-orbit absolute inset-1 rounded-full border border-dashed border-cyan-400/25" /><span className="absolute -right-0.5 top-2 h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,.8)]" /></div>
        <div className="min-w-0 flex-1"><span className="rounded-full border border-cyan-400/25 bg-cyan-500/10 px-2 py-0.5 font-mono text-[9px] uppercase tracking-wider text-cyan-700 dark:text-cyan-300">Team ready</span><h4 className="mt-2 text-[14px] font-semibold tracking-tight text-text-primary">为你找到 {buddies.length} 位学习伙伴</h4><p className="mt-1 line-clamp-2 text-[10px] leading-4 text-text-secondary">{message}</p></div>
      </div>
      <div className="relative mt-4 grid grid-cols-3 gap-2"><HeroMetric label="学习伙伴" value={`${buddies.length} 位`} icon={UserRound} /><HeroMetric label="协作方式" value={`${modes || 1} 种`} icon={HeartHandshake} /><HeroMetric label="优势主题" value={`${topics} 个`} icon={Sparkles} accent /></div>
    </section>
  );
}

function HeroMetric({ label, value, icon: Icon, accent = false }: { label: string; value: string; icon: LucideIcon; accent?: boolean }) {
  return <div className="rounded-lg border border-white/5 bg-bg-base/60 p-2 backdrop-blur-sm"><div className="flex items-center gap-1 text-[9px] text-text-tertiary"><Icon size={10} /><span className="truncate">{label}</span></div><p className={cn('mt-1 truncate text-[12px] font-semibold', accent ? 'text-cyan-600 dark:text-cyan-300' : 'text-text-primary')}>{value}</p></div>;
}

function TwoStagePath({ buddyCount }: { buddyCount: number }) {
  return <section className="student-buddy-enter rounded-xl border border-border-subtle bg-bg-elevated/65 p-3 [animation-delay:70ms]"><div className="flex items-center gap-2"><StageNode icon={Target} step="01" title="组队计划" subtitle="确定主题和协作方式" /><span className="h-px flex-1 bg-gradient-to-r from-cyan-400/50 to-violet-400/30" /><StageNode icon={HeartHandshake} step="02" title="推荐学伴" subtitle={`${buddyCount} 位可一起学习`} /></div></section>;
}

function StageNode({ icon: Icon, step, title, subtitle }: { icon: LucideIcon; step: string; title: string; subtitle: string }) {
  return <div className="flex min-w-0 flex-1 items-center gap-2"><span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-cyan-400/30 bg-cyan-500/10 text-cyan-600 dark:text-cyan-300"><Icon size={14} /></span><div className="min-w-0"><p className="font-mono text-[8px] text-text-tertiary">STEP {step}</p><p className="truncate text-[10px] font-semibold text-text-primary">{title}</p><p className="truncate text-[8px] text-text-tertiary">{subtitle}</p></div></div>;
}

function Avatar({ name, rank }: { name: string; rank: number }) {
  const palette = rank === 1 ? 'from-cyan-400/30 to-blue-500/20 text-cyan-700 dark:text-cyan-200' : rank === 2 ? 'from-violet-400/25 to-indigo-500/15 text-violet-700 dark:text-violet-200' : 'from-amber-400/25 to-orange-500/15 text-amber-700 dark:text-amber-200';
  return <span className={cn('student-buddy-pulse flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-gradient-to-br text-[15px] font-semibold', palette)}>{name.slice(0, 1)}</span>;
}

function BuddyCard({ buddy, index }: { buddy: RecommendedBuddy; index: number }) {
  const rank = buddy.rank ?? index + 1;
  const name = buddy.nickname || `学习伙伴 ${rank}`;
  const role = roleFor(buddy);
  const topics = (buddy.strengths ?? []).slice(0, 4).map(topicLabel);
  return (
    <article className="student-buddy-enter group rounded-xl border border-border-subtle bg-bg-elevated/75 p-3 transition duration-300 hover:-translate-y-0.5 hover:border-cyan-400/35 hover:shadow-[0_12px_28px_rgba(6,182,212,.08)]" style={{ animationDelay: `${130 + index * 90}ms` }}>
      <div className="flex gap-3">
        <div className="relative"><Avatar name={name} rank={rank} /><span className="absolute -bottom-1 -right-1 flex h-5 min-w-5 items-center justify-center rounded-md border border-bg-elevated bg-text-primary px-1 font-mono text-[8px] text-bg-base">{rank}</span></div>
        <div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-1.5"><h5 className="text-[12px] font-semibold text-text-primary">{name}</h5><span className={cn('rounded-full border px-1.5 py-0.5 text-[8px]', role.tone)}>{role.title}</span></div><p className="mt-1 text-[9px] leading-4 text-text-secondary">{role.description}</p>{topics.length > 0 && <div className="mt-2 flex flex-wrap gap-1">{topics.map((topic) => <span key={topic} className="rounded-full border border-border-subtle bg-bg-base/70 px-1.5 py-0.5 text-[9px] text-text-secondary">{topic}</span>)}</div>}<div className="mt-2 rounded-lg border border-violet-400/15 bg-violet-400/5 px-2 py-1.5"><div className="flex items-center gap-1 text-[9px] font-semibold text-violet-700 dark:text-violet-300"><Sparkles size={10} /><span>为什么推荐</span></div><p className="mt-1 text-[9px] leading-4 text-text-secondary">{buddyReason(buddy)}</p></div>{buddy.contact_suggestion && <div className="mt-2 flex items-start gap-1.5 rounded-lg bg-cyan-500/5 px-2 py-1.5 text-[9px] leading-4 text-text-secondary"><MessageCircle size={10} className="mt-0.5 shrink-0 text-cyan-500" /><span>{buddy.contact_suggestion}</span></div>}</div>
      </div>
    </article>
  );
}

function SessionPlan() {
  const steps = [
    { time: '5 min', title: '对齐目标', text: '每个人说出今天最想弄懂的一个问题。' },
    { time: '15 min', title: '轮流讲解', text: '一人讲概念，其他人补充例子或提出疑问。' },
    { time: '10 min', title: '互问互答', text: '用 3 个小问题检查理解，并约定下次主题。' },
  ];
  return (
    <section className="student-buddy-enter rounded-xl border border-violet-400/20 bg-[linear-gradient(135deg,rgba(139,92,246,.08),transparent)] p-3 [animation-delay:400ms]">
      <div className="flex items-center gap-2"><span className="flex h-8 w-8 items-center justify-center rounded-lg bg-violet-500/10 text-violet-600 dark:text-violet-300"><Clock3 size={15} /></span><div><h4 className="text-[10px] font-semibold text-text-primary">第一次学习会 · 30 分钟</h4><p className="text-[9px] text-text-tertiary">照着这个节奏开始，不用担心冷场</p></div></div>
      <div className="mt-3 space-y-2">{steps.map((step, index) => <div key={step.title} className="flex items-start gap-2"><span className="mt-0.5 flex h-5 min-w-10 items-center justify-center rounded-md bg-bg-base px-1 font-mono text-[8px] text-violet-600 dark:text-violet-300">{step.time}</span><div className="min-w-0"><p className="text-[9px] font-semibold text-text-primary">{step.title}</p><p className="text-[9px] leading-4 text-text-secondary">{step.text}</p></div>{index < steps.length - 1 && <span className="ml-auto mt-2 h-px w-3 bg-border-subtle" />}</div>)}</div>
    </section>
  );
}

function SafetyNote() {
  return <div className="student-buddy-enter flex items-start gap-2 rounded-xl border border-border-subtle bg-bg-elevated/60 p-3 [animation-delay:460ms]"><ShieldCheck size={14} className="mt-0.5 shrink-0 text-emerald-500" /><p className="text-[9px] leading-4 text-text-secondary"><span className="font-semibold text-text-primary">友好交流提醒：</span>先围绕学习目标沟通，不分享住址、联系方式等敏感信息；遇到不舒服的交流及时停止并告诉老师。</p></div>;
}

function WaitingState({ isRunning }: { isRunning: boolean }) {
  return <div className="relative flex flex-1 flex-col items-center justify-center overflow-hidden p-6 text-center"><span className="student-buddy-drift absolute h-44 w-44 rounded-full bg-cyan-400/10 blur-3xl" /><div className="relative flex h-20 w-20 items-center justify-center rounded-full border border-cyan-400/25 bg-cyan-500/8 text-cyan-600"><Users size={30} /><span className="student-buddy-radar absolute inset-0 rounded-full border border-cyan-400/30" /><span className="student-buddy-orbit absolute inset-2 rounded-full border border-dashed border-cyan-400/30" /></div><h4 className="relative mt-5 text-[13px] font-semibold text-text-primary">{isRunning ? '正在寻找学习伙伴' : '本轮暂无学伴推荐'}</h4><p className="relative mt-1 max-w-[220px] text-[10px] leading-4 text-text-tertiary">{isRunning ? '正在理解你的学习目标，并寻找适合一起学习的伙伴。' : '发送学伴推荐请求后，这里会出现你的学习小组建议。'}</p></div>;
}

export function StudyBuddyFlow({ onBack, onClose, output, message, isRunning }: Props) {
  const [replayKey, setReplayKey] = useState(0);
  const buddies = useMemo(() => (output?.buddies ?? []).slice(0, 6), [output?.buddies]);
  useEffect(() => { setReplayKey((value) => value + 1); }, [output]);
  return (
    <div className="absolute inset-0 z-30 flex flex-col overflow-hidden bg-bg-base">
      <BuddyMotionStyles />
      <Header onBack={onBack} onClose={onClose} />
      <div key={replayKey} className="min-h-0 flex-1 overflow-y-auto px-3 pb-6 pt-3 [scrollbar-width:thin]">
        {output ? <div className="space-y-3"><Hero message={message || '本轮学伴推荐请求'} buddies={buddies} /><TwoStagePath buddyCount={buddies.length} /><div className="flex items-center justify-between px-0.5"><h4 className="text-[11px] font-semibold text-text-primary">推荐学伴</h4><span className="text-[9px] text-text-tertiary">选择最想先认识的一位</span></div><div className="space-y-2">{buddies.map((buddy, index) => <BuddyCard key={`${buddy.user_id}-${index}`} buddy={buddy} index={index} />)}</div><SessionPlan /><SafetyNote /></div> : <WaitingState isRunning={isRunning} />}
      </div>
    </div>
  );
}

export default StudyBuddyFlow;
