/**
 * AgentInteractionLog
 *
 * 原 ThinkingView.tsx 的升级版:把每条 step 渲染成 "Agent Trace Block"。
 *
 * 数据来源:
 *   - chatStore.thinkingSteps: 流式期间累积的 step 数组(主要数据源)
 *   - chatStore.currentTurn.agentTimeline: 提供时间戳 / agentLabel
 *   - chatStore.currentFocusAgents: 用于判断 isRoundHighlight(本轮重点)
 *
 * 兼容: 默认导出仍叫 ThinkingView(原 ChatContainer 用),保留折叠交互。
 *
 * agent 输出 JSON 里若存在 decision / next_agents / workflow_type 字段,
 * 用 grid 显示在 block 底部。
 *
 * 底部"正在运行 xxx"进度条: 保留,颜色改 bg-accent,高度 2px。
 */

import { useState, useEffect, useRef } from 'react';
import { Ban, ChevronDown, ChevronRight, Cpu, GraduationCap, ShieldCheck, Sparkles } from 'lucide-react';
import { cn } from '@/utils/cn';
import { renderValue } from '@/utils/jsonTree';
import { useChatStore } from '@/stores/chatStore';
import { AGENT_CONFIGS } from '@/data/agentConfigs';
import type { ThinkingStep } from '@/types';

/* ── 工具:从 step.content(可能是 JSON 字符串)里抽关键字段 ───── */

interface ExtractedFields {
  decision?: unknown;
  next_agents?: unknown;
  workflow_type?: unknown;
}

type SafetyBranch = 'PASS' | 'REJECT' | 'GUIDE';

function SafetyBranchFlow({ value }: { value: Record<string, unknown> }) {
  const branch = String(value.raw_branch ?? '').toUpperCase() as SafetyBranch;
  if (!['PASS', 'REJECT', 'GUIDE'].includes(branch)) return null;

  const safetyContext =
    typeof value.safety_context === 'object' && value.safety_context !== null
      ? (value.safety_context as Record<string, unknown>)
      : {};
  const guide =
    typeof safetyContext.guidance_skill === 'object' && safetyContext.guidance_skill !== null
      ? (safetyContext.guidance_skill as Record<string, unknown>)
      : null;
  const classifier =
    typeof safetyContext.classifier === 'object' && safetyContext.classifier !== null
      ? (safetyContext.classifier as Record<string, unknown>)
      : {};
  const options = Array.isArray(guide?.learning_options)
    ? guide.learning_options.map(String)
    : [];
  const recommendedOption = String(guide?.recommended_option ?? '');
  const branches: Array<{ id: SafetyBranch; label: string; Icon: typeof ShieldCheck }> = [
    { id: 'PASS', label: '进入学习', Icon: ShieldCheck },
    { id: 'REJECT', label: '安全回应', Icon: Ban },
    { id: 'GUIDE', label: '教育引导', Icon: GraduationCap },
  ];

  return (
    <div className="mb-2 border-b border-border-subtle pb-2">
      <div className="grid grid-cols-3 gap-2">
        {branches.map(({ id, label, Icon }) => {
          const active = branch === id;
          return (
            <div
              key={id}
              className={cn(
                'flex items-center gap-1.5 rounded-md border px-2 py-1.5 text-12',
                active
                  ? 'border-accent/40 bg-accent-soft text-accent'
                  : 'border-border-subtle bg-bg-base text-text-tertiary',
              )}
            >
              <Icon size={14} strokeWidth={1.5} />
              <span>{label}</span>
            </div>
          );
        })}
      </div>
      <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 rounded-md border border-border-subtle bg-bg-base px-2 py-2 text-11 sm:grid-cols-3">
        <span className="text-text-tertiary">
          决策来源：<b className="font-mono font-normal text-text-secondary">{String(classifier.decision_source ?? 'unknown')}</b>
        </span>
        <span className="text-text-tertiary">
          主模型：<b className="font-mono font-normal text-text-secondary">{String(classifier.primary_model_status ?? 'unknown')}</b>
        </span>
        <span className="text-text-tertiary">
          裁决原因：<b className="font-mono font-normal text-text-secondary">{String(classifier.adjudication_reason ?? '无')}</b>
        </span>
        <span className="text-text-tertiary">
          对象：<b className="font-mono font-normal text-text-secondary">{String(classifier.target_type ?? 'unknown')}</b>
        </span>
        <span className="text-text-tertiary">
          程度：<b className="font-mono font-normal text-text-secondary">{String(classifier.harm_severity ?? 'none')}</b>
        </span>
        <span className="text-text-tertiary">
          请求：<b className="font-mono font-normal text-text-secondary">{String(classifier.request_type ?? 'unknown')}</b>
        </span>
      </div>
      {branch === 'GUIDE' && guide && (
        <div className="mt-2 rounded-md border border-border-subtle bg-bg-base px-2 py-2">
          <div className="flex items-center gap-1.5 text-12 text-text-secondary">
            <GraduationCap size={14} strokeWidth={1.5} />
            <span>📘 已整理为两阶段学习路径</span>
          </div>
          {options.length > 0 && (
            <ol className="mt-1 list-decimal space-y-0.5 pl-5 text-12 text-text-tertiary">
              {options.map((option) => (
                <li key={option}>
                  {option}{option === recommendedOption ? '（✨ 推荐起点）' : ''}
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </div>
  );
}

function extractFields(content: string): ExtractedFields | null {
  let parsed: unknown = content;
  try {
    parsed = JSON.parse(content);
  } catch {
    return null;
  }
  if (typeof parsed !== 'object' || parsed === null) return null;
  const obj = parsed as Record<string, unknown>;
  const keys = ['decision', 'next_agents', 'workflow_type'];
  const has = keys.some((k) => k in obj);
  if (!has) return null;
  const out: ExtractedFields = {};
  if ('decision' in obj) out.decision = obj.decision;
  if ('next_agents' in obj) out.next_agents = obj.next_agents;
  if ('workflow_type' in obj) out.workflow_type = obj.workflow_type;
  return out;
}

/* ── 单个 Agent Trace Block ───────────────────────────────── */

function AgentTraceBlock({
  step,
  idx,
  isActive,
  isRunning,
  isRoundHighlight,
  showConnector,
  isHighlighted,
}: {
  step: ThinkingStep;
  idx: number;
  isActive: boolean;
  isRunning: boolean;
  isRoundHighlight: boolean;
  showConnector: boolean;
  isHighlighted?: boolean;
}) {
  const [open, setOpen] = useState(true);

  // agent 内部名(step.step)和显示名(label)
  const agentName = step.step || '';
  const config = agentName ? AGENT_CONFIGS[agentName] : undefined;
  const displayLabel = config?.displayName || step.label || agentName || 'unknown';
  // avatar 缩写:displayName 首字
  const avatar = (displayLabel?.[0] || '?').toUpperCase();

  // parse content 抽取展示
  let parsed: unknown = step.content;
  try {
    parsed = JSON.parse(step.content);
  } catch {
    parsed = step.content;
  }
  const fields = step.content ? extractFields(step.content) : null;

  // 稳定的 DOM id,供外部 scrollIntoView 定位
  const blockId = `trace-block-${step.step || 'unknown'}-${idx}`;

  return (
    <div
      id={blockId}
      className={cn(
        'relative flex gap-3 px-3 py-2 transition-shadow duration-300',
        isHighlighted && 'ring-2 ring-accent/60 rounded-md',
      )}
    >
      {/* 左侧 avatar + 连接线 */}
      <div className="relative flex flex-col items-center">
        <div
          className={cn(
            'flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-12 font-display',
            isRoundHighlight
              ? 'border-accent/40 bg-accent-soft text-accent'
              : 'border-border-subtle bg-bg-elevated text-text-secondary',
          )}
        >
          {avatar}
        </div>
        {showConnector && (
          <div
            className="absolute top-6 h-[calc(100%-1.5rem)] w-px"
            style={{
              borderLeft: '0.5px dashed var(--color-border-subtle)',
            }}
          />
        )}
      </div>

      {/* 右侧内容框 */}
      <div
        className={cn(
          'relative flex-1 rounded-md border px-3 py-2 transition-colors',
          isRoundHighlight
            ? 'border-accent/30 bg-bg-elevated'
            : 'border-border-subtle bg-bg-elevated/50',
        )}
        style={
          isRoundHighlight
            ? {
                boxShadow:
                  'inset 0 0 0 1.5px transparent',
                backgroundImage:
                  'linear-gradient(var(--color-bg-elevated), var(--color-bg-elevated)), linear-gradient(135deg, var(--color-accent), transparent)',
                backgroundOrigin: 'border-box',
                backgroundClip: 'padding-box, border-box',
              }
            : undefined
        }
      >
        {/* 顶部标题行 */}
        <button
          type="button"
          onClick={() => !isRunning && setOpen((v) => !v)}
          className="flex w-full items-center gap-2 text-left"
        >
          <span className="text-14 font-display font-medium text-text-primary">
            {displayLabel}
          </span>
          {isRoundHighlight && (
            <span className="inline-flex items-center gap-1 rounded-sm bg-accent-soft px-1.5 py-0.5 text-12 text-accent">
              <Sparkles size={12} />
              本轮重点
            </span>
          )}
          {isRunning && (
            <span className="ml-auto inline-flex items-center gap-1 text-12 text-text-tertiary">
              <span className="h-1 w-1 animate-pulse rounded-full bg-accent" />
              running
            </span>
          )}
          {!isRunning && (
            <span className="ml-auto text-text-tertiary">
              {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            </span>
          )}
        </button>

        {/* 运行中进度条 */}
        {isRunning && (
          <div className="mt-2 h-0.5 w-full overflow-hidden rounded-full bg-bg-base">
            <div
              className="h-full rounded-full bg-accent"
              style={{
                background:
                  'linear-gradient(90deg, transparent, var(--color-accent), transparent)',
                backgroundSize: '200% 100%',
                animation: 'progress 1.5s ease-in-out infinite',
              }}
            />
          </div>
        )}

        {/* 内容渲染(沿用 renderValue) */}
        {!isRunning && open && (
          <div className="mt-2 text-12 leading-relaxed text-text-secondary">
            {agentName === 'safety_monitor' && typeof parsed === 'object' && parsed !== null && (
              <SafetyBranchFlow value={parsed as Record<string, unknown>} />
            )}
            {renderValue(parsed)}
          </div>
        )}

        {/* 关键字段 grid */}
        {!isRunning && open && fields && (
          <div className="mt-2 grid grid-cols-3 gap-2 border-t border-border-subtle pt-2">
            {fields.decision !== undefined && (
              <div className="flex flex-col">
                <span className="text-11 uppercase tracking-wide text-text-tertiary">
                  decision
                </span>
                <span className="text-12 font-mono text-text-primary">
                  {String(fields.decision)}
                </span>
              </div>
            )}
            {fields.next_agents !== undefined && (
              <div className="flex flex-col">
                <span className="text-11 uppercase tracking-wide text-text-tertiary">
                  next_agents
                </span>
                <span className="text-12 font-mono text-text-primary">
                  {Array.isArray(fields.next_agents)
                    ? fields.next_agents.join(', ')
                    : String(fields.next_agents)}
                </span>
              </div>
            )}
            {fields.workflow_type !== undefined && (
              <div className="flex flex-col">
                <span className="text-11 uppercase tracking-wide text-text-tertiary">
                  workflow_type
                </span>
                <span className="text-12 font-mono text-text-primary">
                  {String(fields.workflow_type)}
                </span>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/* ── 主组件(对外同时以 ThinkingView / AgentInteractionLog 暴露) ── */

interface Props {
  steps: ThinkingStep[];
}

export function AgentInteractionLog({ steps }: Props) {
  const [expanded, setExpanded] = useState(true);
  const containerRef = useRef<HTMLDivElement>(null);
  const focusAgents = useChatStore((s) => s.currentFocusAgents);

  // 被外部 Trace Timeline 点击触发的短暂高亮 key
  const [highlightedKey, setHighlightedKey] = useState<string | null>(null);

  useEffect(() => {
    if (expanded && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [steps.length, expanded]);

  // 监听 AgentStudio Trace Timeline 的点击事件:
  // 滚到对应 block + 短暂高亮 2s
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail as {
        agentName: string;
        idx?: number;
      };
      if (!detail?.agentName) return;

      // 在当前 steps 里找第一个匹配 agentName 的 index
      const stepIdx = steps.findIndex((s) => s.step === detail.agentName);
      if (stepIdx < 0) return; // 还没收到对应 step,静默忽略

      // 自动展开(否则 block 不在 DOM 里,没法滚)
      setExpanded(true);

      // 等 React 重渲染后再 scrollIntoView
      requestAnimationFrame(() => {
        const blockEl = document.getElementById(
          `trace-block-${detail.agentName}-${stepIdx}`,
        );
        blockEl?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      });

      // 短暂高亮 2s 后清除(仅当还是当前 key 时才清,避免快速连点把后一个也清掉)
      const key = `${detail.agentName}-${stepIdx}`;
      setHighlightedKey(key);
      window.setTimeout(() => {
        setHighlightedKey((cur) => (cur === key ? null : cur));
      }, 2000);
    };

    window.addEventListener('agent-studio:focus-trace', handler);
    return () => window.removeEventListener('agent-studio:focus-trace', handler);
  }, [steps]);

  if (steps.length === 0) return null;

  return (
    <div>
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center gap-1.5 rounded-md px-1 py-1 text-12 text-text-secondary hover:text-text-primary transition-colors"
      >
        <Cpu size={13} className="text-text-tertiary" />
        <span className="font-medium">思考过程</span>
        <span className="ml-auto">
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </span>
      </button>

      {expanded && (
        <div
          ref={containerRef}
          className="mt-1 max-h-72 overflow-y-auto rounded-md border border-border-subtle bg-bg-base/50 scrollbar-thin"
        >
          {steps.map((step, idx) => {
            const agentName = step.step || '';
            const isRoundHighlight = focusAgents.includes(agentName);
            const key = `${agentName}-${idx}`;
            return (
              <AgentTraceBlock
                key={idx}
                idx={idx}
                step={step}
                isActive={idx === steps.length - 1}
                isRunning={step.status === 'running'}
                isRoundHighlight={isRoundHighlight}
                showConnector={idx < steps.length - 1}
                isHighlighted={highlightedKey === key}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}

/* 向后兼容:原 ChatContainer 引用 ThinkingView,保留命名导出 */
export const ThinkingView = AgentInteractionLog;

export default AgentInteractionLog;
