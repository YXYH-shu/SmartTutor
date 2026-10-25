/**
 * AgentStudio
 *
 * 三段式智能体面板:
 *   段一 Hero Slot   (40% 高度): 1-2 个本轮重点 agent 大卡 + 渐变描边 + 本轮实际输出 grid
 *   段二 Ensemble Rail (40% 高度): 其余协作 agent 卡片列表(两行信息,可点击)
 *   段三 Trace Timeline (20% 高度): agent 调用时间线
 *
 * 数据:
 *   - chatStore.currentFocusAgents / currentTurn.agentTimeline / activeNodeId
 *     / agentTrace / selectedDetailAgent
 *   - AGENT_CONFIGS + AGENT_HIGHLIGHT_FIELDS(静态 + 字段定义)
 *
 * 交互:
 *   - 任何 agent 卡片点击 → chatStore.setSelectedDetailAgent(name)
 *   - AgentInfoPanel 内 absolute 浮层 AgentDetailDrawer 渲染详情
 *   - Trace Timeline 点击节点同时 emit 'agent-studio:focus-trace' CustomEvent,
 *     AgentInteractionLog 监听后 scrollIntoView
 *
 * 呼吸光晕互斥(全局唯一活跃):
 *   - Hero Slot 的呼吸动画条件 = !activeNodeId(Path Bar active 时停止呼吸)
 */

import { Sparkles } from 'lucide-react';
import { useChatStore } from '@/stores/chatStore';
import { AGENT_CONFIGS, AGENT_DISPLAY_ORDER, AGENT_HIGHLIGHT_FIELDS } from '@/data/agentConfigs';
import { getIcon, getValueByPath, parseAgentContent } from './agentUtils';
import { cn } from '@/utils/cn';
import type { AgentTimelineItem } from '@/types';
import { LearningModuleSummaryCard } from './learning-modules/LearningModuleSummaryCard';

// 模块级空数组常量,避免 selector 用 ?? [] 每次创建新引用导致 useSyncExternalStore 死循环
const EMPTY_TIMELINE: AgentTimelineItem[] = [];

/* ──────────────────── Hero Slot: 本轮输出子组件 ──────────────────── */

function HeroOutputSection({ name }: { name: string }) {
  const agentTrace = useChatStore((s) => s.agentTrace);
  const traceEntry = agentTrace[name];
  const fields = AGENT_HIGHLIGHT_FIELDS[name] ?? [];

  if (!traceEntry?.content) {
    return <p className="text-12 italic text-text-tertiary">等待执行...</p>;
  }

  const parsed = parseAgentContent(traceEntry.content);
  if (!parsed) {
    // 非对象(纯文本),展示前 80 字符
    return (
      <p className="line-clamp-2 text-12 text-text-secondary">{traceEntry.content.slice(0, 80)}</p>
    );
  }

  if (fields.length === 0) {
    return (
      <p className="line-clamp-2 text-12 text-text-secondary">{traceEntry.content.slice(0, 80)}</p>
    );
  }

  return (
    <div className="grid grid-cols-2 gap-1.5">
      {fields.map((f) => {
        const raw = getValueByPath(parsed, f.key);
        const value = f.format ? f.format(raw) : String(raw ?? '-');
        return (
          <div key={f.key} className="flex flex-col">
            <span className="font-mono text-11 uppercase tracking-wide text-text-tertiary">
              {f.label}
            </span>
            <span className="font-mono text-12 text-text-primary tabular-nums">{value}</span>
          </div>
        );
      })}
    </div>
  );
}

/* ───────────────────────── 段一 Hero Slot ───────────────────────── */

function HeroSlot() {
  const focusAgents = useChatStore((s) => s.currentFocusAgents);
  const activeNodeId = useChatStore((s) => s.activeNodeId);
  const setSelectedDetailAgent = useChatStore((s) => s.setSelectedDetailAgent);

  // 最多 2 个 hero(防止 3+ 个挤爆)
  const heroes = focusAgents.slice(0, 2);

  if (heroes.length === 0) {
    return (
      <div className="flex h-full min-h-[140px] flex-col items-center justify-center gap-3 px-4 py-4">
        {/* SVG 协作拓扑:中心决策模型 + 5 个子节点连线 */}
        <svg viewBox="0 0 200 120" className="h-24 w-full max-w-[200px]" aria-hidden>
          {/* 中心节点 */}
          <circle cx="100" cy="60" r="14" fill="none" stroke="var(--color-text-tertiary)" strokeWidth="1" />
          <text x="100" y="64" textAnchor="middle" fontSize="9" fill="var(--color-text-tertiary)">
            决策
          </text>
          {/* 5 个子节点环形 */}
          {[0, 1, 2, 3, 4].map((i) => {
            const angle = (i / 5) * Math.PI * 2 - Math.PI / 2;
            const x = 100 + 40 * Math.cos(angle);
            const y = 60 + 32 * Math.sin(angle);
            return (
              <g key={i}>
                <line
                  x1="100"
                  y1="60"
                  x2={x}
                  y2={y}
                  stroke="var(--color-border-subtle)"
                  strokeWidth="0.5"
                  strokeDasharray="2 2"
                />
                <circle cx={x} cy={y} r="6" fill="none" stroke="var(--color-text-tertiary)" strokeWidth="1" />
              </g>
            );
          })}
        </svg>
        <p className="text-center text-12 text-text-tertiary">发送问题后,系统将自动调度最适合的智能体组合</p>
      </div>
    );
  }

  return (
    <div className={cn("flex h-full flex-col gap-2 px-3 py-3", heroes.some((name) => name === 'cognitive_diagnosis' || name === 'learning_path') && 'learning-summary-list')}>
      {heroes.map((name) => {
        if (name === 'cognitive_diagnosis' || name === 'learning_path') {
          return <LearningModuleSummaryCard key={name} name={name} />;
        }
        const cfg = AGENT_CONFIGS[name];
        if (!cfg) return null;
        const Icon = getIcon(cfg.icon);
        // 互斥:Path Bar active 时 Hero 不呼吸
        const breathe = !activeNodeId;
        return (
          <button
            key={name}
            type="button"
            onClick={() => setSelectedDetailAgent(name)}
            className="group relative flex flex-1 flex-col overflow-hidden rounded-lg bg-bg-elevated p-3 text-left shadow-3 transition-transform duration-200 ease-spring hover:scale-[1.01]"
            style={{
              backgroundImage:
                'linear-gradient(var(--color-bg-elevated), var(--color-bg-elevated)), linear-gradient(135deg, var(--color-accent), transparent 60%)',
              backgroundOrigin: 'border-box',
              backgroundClip: 'padding-box, border-box',
              border: '1.5px solid transparent',
            }}
          >
            {/* 静态径向光晕(即使 breathe 停了也有发光感) */}
            <div
              className="pointer-events-none absolute -inset-4 -z-10 opacity-50"
              style={{
                background: 'radial-gradient(circle at 30% 30%, var(--color-accent-glow) 0%, transparent 70%)',
              }}
            />
            {/* 顶部徽章 */}
            <span className="absolute right-2 top-2 inline-flex items-center gap-1 rounded-sm bg-accent-soft px-1.5 py-0.5 text-12 text-accent">
              <Sparkles size={12} />
              本轮重点
            </span>

            {/* 主体:上面 icon + 名称,下面本轮输出 grid */}
            <div className="mb-2 flex items-center gap-3">
              <div
                className={cn(
                  'flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-accent-soft text-accent',
                  breathe && 'animate-breathe',
                )}
              >
                <Icon size={20} />
              </div>
              <h3 className="flex-1 text-18 font-display font-semibold tracking-tight text-text-primary">
                {cfg.displayName}
              </h3>
            </div>

            {/* 本轮输出 grid */}
            <HeroOutputSection name={name} />
          </button>
        );
      })}
    </div>
  );
}

/* ─────────────────────── 段二 Ensemble Rail ─────────────────────── */

function EnsembleCard({
  name,
  status,
}: {
  name: string;
  status?: 'running' | 'completed' | 'pending' | 'error';
}) {
  const cfg = AGENT_CONFIGS[name];
  const setSelectedDetailAgent = useChatStore((s) => s.setSelectedDetailAgent);
  if (!cfg) return null;
  const Icon = getIcon(cfg.icon);
  const tokK = Math.round(cfg.llmConfig.maxTokens / 1000);

  // 状态灯颜色
  const dotClass =
    status === 'running'
      ? 'bg-accent animate-pulse'
      : status === 'completed'
        ? 'bg-status-success'
        : status === 'error'
          ? 'bg-status-error'
          : 'bg-text-tertiary opacity-60';

  return (
    <button
      type="button"
      onClick={() => setSelectedDetailAgent(name)}
      className="group flex w-full flex-col gap-0.5 rounded-md border border-border-subtle bg-bg-base px-3 py-2 text-left transition-all duration-200 ease-spring hover:border-border-strong hover:bg-bg-elevated"
    >
      {/* 第一行:状态灯 + icon + 中文名 + model · T */}
      <div className="flex items-center gap-2">
        <span className={cn('inline-block h-1.5 w-1.5 shrink-0 rounded-full', dotClass)} />
        <Icon size={12} className="shrink-0 text-text-secondary" />
        <span className="flex-1 truncate text-13 text-text-primary">{cfg.displayName}</span>
        <span className="font-mono text-11 text-text-tertiary">
          {cfg.llmConfig.model} · T{cfg.llmConfig.temperature}
        </span>
      </div>
      {/* 第二行:Token · timeout · thinking */}
      <div className="pl-3.5 font-mono text-11 text-text-tertiary">
        {tokK}K · {cfg.llmConfig.timeout}s · think {cfg.llmConfig.thinking ? 'on' : 'off'}
      </div>
    </button>
  );
}

function EnsembleRail() {
  const agentTimeline = useChatStore((s) => s.currentTurn?.agentTimeline ?? EMPTY_TIMELINE);
  const focusAgents = useChatStore((s) => s.currentFocusAgents);

  // 排除 focusAgents(已上 Hero) + 只保留 AGENT_CONFIGS 里有的 + 去重(保留第一次出现)
  const others = agentTimeline
    .filter((it) => !focusAgents.includes(it.agentName) && AGENT_CONFIGS[it.agentName])
    .filter((it, idx, arr) => arr.findIndex((x) => x.agentName === it.agentName) === idx);

  return (
    <div className="flex h-full flex-col gap-2 px-3 py-3">
      <p className="text-11 uppercase tracking-wide text-text-tertiary">
        其余协作 agent(本轮 {others.length} 个)
      </p>
      <div className="flex-1 space-y-1.5 overflow-y-auto scrollbar-thin">
        {others.length === 0 ? (
          <div className="space-y-1">
            <p className="mb-1 text-11 text-text-tertiary">以下智能体待命中</p>
            {AGENT_DISPLAY_ORDER.filter((n) => AGENT_CONFIGS[n]).map((n) => {
              const cfg = AGENT_CONFIGS[n];
              const Icon = getIcon(cfg.icon);
              return (
                <div
                  key={n}
                  className="flex items-center gap-2 rounded-md border border-border-subtle/50 bg-bg-base/30 px-3 py-1.5"
                >
                  <span className="inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-text-tertiary opacity-40" />
                  <Icon size={12} className="shrink-0 text-text-tertiary" />
                  <span className="flex-1 truncate text-12 text-text-tertiary">{cfg.displayName}</span>
                  <span className="font-mono text-11 text-text-tertiary/70">{cfg.llmConfig.model}</span>
                </div>
              );
            })}
          </div>
        ) : (
          others.map((item) => (
            <EnsembleCard key={item.agentName} name={item.agentName} status={item.status} />
          ))
        )}
      </div>
    </div>
  );
}

/* ─────────────────────── 段三 Trace Timeline ────────────────────── */

function TraceTimeline() {
  const agentTimeline = useChatStore((s) => s.currentTurn?.agentTimeline ?? EMPTY_TIMELINE);
  const focusAgents = useChatStore((s) => s.currentFocusAgents);
  const setSelectedDetailAgent = useChatStore((s) => s.setSelectedDetailAgent);

  const handleNodeClick = (agentName: string, idx: number) => {
    // 只对真正 agent(在 AGENT_CONFIGS 里)打开抽屉;聚合节点(knowledge_responder 等)只滚动不开抽屉
    if (AGENT_CONFIGS[agentName]) {
      setSelectedDetailAgent(agentName);
    }
    // 同时 emit custom event 让 AgentInteractionLog 滚动(已有逻辑保留)
    if (typeof window !== 'undefined') {
      window.dispatchEvent(
        new CustomEvent('agent-studio:focus-trace', {
          detail: { agentName, idx },
        }),
      );
    }
  };

  if (agentTimeline.length === 0) {
    return (
      <div className="flex h-full items-center px-3 py-2">
        <div className="flex flex-col items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-full border border-border-strong bg-bg-base" />
          <span className="h-16 w-px border-l border-dashed border-border-subtle" />
          <span className="text-11 text-text-tertiary">等待首次调用</span>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto px-3 py-2 scrollbar-thin">
      <ul className="relative flex flex-col">
        {agentTimeline.map((item, idx) => {
          const isFocus = focusAgents.includes(item.agentName);
          const ts = new Date(item.startedAt);
          const time = ts.toLocaleTimeString('zh-CN', { hour12: false }) || '';
          return (
            <li key={`${item.agentName}-${idx}`} className="relative flex items-center gap-2 pb-2">
              {/* 竖线 */}
              {idx < agentTimeline.length - 1 && (
                <span
                  className="absolute left-[3px] top-3 h-[calc(100%-0.5rem)] w-px"
                  style={{ borderLeft: '0.5px dashed var(--color-border-subtle)' }}
                />
              )}
              {/* 圆点 */}
              <button
                type="button"
                onClick={() => handleNodeClick(item.agentName, idx)}
                className={cn(
                  'inline-block h-2 w-2 shrink-0 rounded-full border-2 transition-all duration-200',
                  isFocus ? 'border-accent bg-accent' : 'border-border-strong bg-bg-base',
                )}
                aria-label={`trace ${item.agentName}`}
              />
              <span className="font-mono text-11 text-text-tertiary">{time}</span>
              <span
                className={cn(
                  'truncate text-12',
                  isFocus ? 'text-accent' : 'text-text-secondary',
                )}
              >
                {(item.agentLabel?.replace(/^正在运行/, '')) || AGENT_CONFIGS[item.agentName]?.displayName || item.agentName}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/* ─────────────────────── 主面板 ─────────────────────── */

/**
 * AgentStudio 三段式主面板。
 * 外层折叠容器、Header 由 AgentInfoPanel.tsx 提供,这里只是内部滚动内容。
 */
export function AgentStudio() {
  return (
    <div className="flex h-full flex-col">
      {/* 段一 Hero Slot 40% */}
      <section className="flex h-[40%] min-h-[140px] flex-col">
        <HeroSlot />
      </section>
      <div className="h-px bg-border-subtle" />
      {/* 段二 Ensemble Rail 40% */}
      <section className="flex h-[40%] min-h-[140px] flex-col">
        <EnsembleRail />
      </section>
      <div className="h-px bg-border-subtle" />
      {/* 段三 Trace Timeline 20% */}
      <section className="flex h-[20%] min-h-[80px] flex-col">
        <TraceTimeline />
      </section>
    </div>
  );
}

export default AgentStudio;
