/**
 * 机制流程图（参考项目介绍图：输入 → 处理 → 决策 → 出口），按 320px 右栏设计。
 * 本轮实际走过的节点高亮，箭头上有光点流动。纯展示，不读 store。
 */
import {
  Ban,
  Compass,
  FilePenLine,
  FileSearch,
  MessageSquareText,
  MousePointerClick,
  RefreshCcw,
  ScanSearch,
  ShieldCheck,
  Sparkles,
  Stethoscope,
  type LucideIcon,
} from 'lucide-react';
import { cn } from '@/utils/cn';
import { delay } from './motion';
import { TONE_CHIP, type Tone } from './primitives';
import type { CorrectorAction, SafetyBranch, SafetyMode } from './types';

const OFF = 'border-border-subtle bg-bg-base text-text-tertiary';

function Box({
  icon: Icon,
  title,
  sub,
  on,
  tone = 'accent',
  index = 0,
}: {
  icon: LucideIcon;
  title: string;
  sub?: string;
  on: boolean;
  tone?: Tone;
  index?: number;
}) {
  return (
    <div
      className={cn(
        't43-rise flex flex-col items-center gap-0.5 rounded-md border px-1.5 py-1.5 text-center transition-colors',
        on ? TONE_CHIP[tone] : OFF,
      )}
      style={delay(index, 90, 60)}
    >
      <Icon size={14} strokeWidth={1.75} className={on ? undefined : 'opacity-60'} />
      <div className={cn('text-12 leading-tight', on && 'font-medium')}>{title}</div>
      {sub && <div className="text-11 leading-tight opacity-75">{sub}</div>}
    </div>
  );
}

/** 向下的连线；on 时有光点沿线流动 */
function Link({ on, index = 0 }: { on: boolean; index?: number }) {
  return (
    <div className="relative mx-auto h-4 w-px overflow-hidden bg-border-subtle">
      {on && <span className="t43-flow absolute left-0 top-0 h-2 w-px bg-accent" style={delay(index, 140)} />}
    </div>
  );
}

function Frame({ children }: { children: React.ReactNode }) {
  return (
    <div className="t43-rise mb-4 rounded-lg border border-dashed border-border-strong bg-bg-base/60 p-2.5">
      <div className="mb-2 flex items-baseline justify-between gap-2">
        <span className="text-12 font-display font-semibold text-text-primary">工作机制</span>
        <span className="text-11 text-text-tertiary">亮色 = 本轮路径</span>
      </div>
      {children}
    </div>
  );
}

export function SafetyMechanism({ branch, mode }: { branch: SafetyBranch | ''; mode: SafetyMode }) {
  const classified = mode === 'classified';
  return (
    <Frame>
      <Box icon={MessageSquareText} title="当前问题 + 学段 + 最近对话" on index={0} tone="info" />
      <Link on index={0} />
      <Box
        icon={classified ? ScanSearch : MousePointerClick}
        title={classified ? '主分类 + 规则 / 疑难复核' : '选项匹配'}
        sub={classified ? undefined : '学生点选了系统给的选项，免风险分类'}
        on
        index={1}
        tone={classified ? 'accent' : 'info'}
      />
      <Link on index={1} />
      <div className="grid grid-cols-3 gap-1.5">
        <Box icon={ShieldCheck} title="放行" sub="原教学" on={branch === 'PASS'} tone="success" index={2} />
        <Box icon={Compass} title="引导" sub="学科→知识点" on={branch === 'GUIDE'} tone="accent" index={3} />
        <Box icon={Ban} title="拒绝" sub="安全回应" on={branch === 'REJECT'} tone="error" index={4} />
      </div>
      {branch === 'GUIDE' && (
        <>
          <Link on index={2} />
          <Box
            icon={Sparkles}
            title="教育转化 Skill"
            sub={classified ? '先选学科，再选知识点' : '已选学科，进入知识点选择'}
            on
            index={5}
          />
        </>
      )}
      {branch === 'PASS' && mode === 'focus_chosen' && (
        <>
          <Link on index={2} />
          <Box icon={Stethoscope} title="携带安全约束进入教学" sub="诊断 / 资源推荐 / 知识问答" on index={5} tone="success" />
        </>
      )}
    </Frame>
  );
}

export function CorrectorMechanism({ action }: { action: CorrectorAction | '' }) {
  return (
    <Frame>
      <Box icon={FileSearch} title="原回答 + 问题 + 学科学段 + 安全约束" on index={0} tone="info" />
      <Link on index={0} />
      <Box icon={Stethoscope} title="教育性质量自检" sub="科学论证 · 元认知引导 · 科学话语 · 内容安全" on index={1} />
      <Link on={action !== ''} index={1} />
      <div className="grid grid-cols-3 gap-1.5">
        <Box icon={ShieldCheck} title="PASS" sub="保留原文" on={action === 'PASS'} tone="success" index={2} />
        <Box icon={FilePenLine} title="PATCH" sub="保留结构" on={action === 'PATCH'} tone="warning" index={3} />
        <Box icon={RefreshCcw} title="退回重写" sub="限制次数" on={action === 'REGENERATE'} tone="error" index={4} />
      </div>
    </Frame>
  );
}
