import { useState, useEffect, useRef } from 'react';
import { ChevronDown, ChevronRight, Cpu } from 'lucide-react';
import { cn } from '@/utils/cn';
import type { ThinkingStep } from '@/types';

/* ── Key name translation ──────────────────────────────────── */

const KEY_LABELS: Record<string, string> = {
  action: '动作',
  raw_action: '原始动作',
  safety_context: '安全上下文',
  blocked_response: '拦截回复',
  transformed_message: '转换后消息',
  emotion: '情绪',
  intensity: '强度',
  trend: '趋势',
  decision: '决策',
  next_agents: '下一步智能体',
  workflow_type: '工作流类型',
  current_stage: '当前阶段',
  stage_counter: '阶段计数',
  agent: '智能体',
  agent_output: '智能体输出',
  remaining_agents: '剩余智能体',
  accumulated_outputs: '累积输出',
  final_response_preview: '回复预览',
  emotion_state: '情感状态',
  summary: '摘要',
  score: '分数',
  level: '等级',
  type: '类型',
  content: '内容',
  name: '名称',
  description: '描述',
  topic: '主题',
  status: '状态',
  reason: '原因',
  confidence: '置信度',
  mastery_level: '掌握程度',
  weak_points: '薄弱点',
  recommendation: '建议',
  knowledge_states: '知识状态',
  resources: '资源',
  difficulty: '难度',
  encouragement: '鼓励',
  tips: '提示',
  empathy_response: '共情回复',
  polished_content: '润色内容',
  tags: '标签',
  category: '分类',
  details: '详情',
  value: '值',
  key: '键',
  step: '步骤',
  label: '标签',
  knowledge_graph: '知识图谱',
  learning_style: '学习风格',
  preferences: '偏好',
  goal: '目标',
  plan: '计划',
  duration: '时长',
  priority: '优先级',
  feedback: '反馈',
  question: '问题',
  answer: '答案',
  explanation: '解释',
  hint: '提示',
  resource: '资源',
  url: '链接',
  title: '标题',
};

function translateKey(key: string): string {
  return KEY_LABELS[key] || key;
}

/* ── Recursive value renderer ──────────────────────────────── */

function renderValue(value: unknown, depth = 0): React.ReactNode {
  if (depth > 6) return <span className="text-gray-400">…</span>;

  if (value === null || value === undefined) {
    return <span className="text-gray-400">-</span>;
  }
  if (typeof value === 'boolean') {
    return <span className="text-blue-500">{value ? '是' : '否'}</span>;
  }
  if (typeof value === 'number') {
    return <span className="text-amber-600 dark:text-amber-400">{value}</span>;
  }
  if (typeof value === 'string') {
    if (value.length > 400) {
      return <span>{value.slice(0, 400)}…</span>;
    }
    return value;
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-gray-400">(空)</span>;
    if (value.every((v) => typeof v === 'string' && v.length < 30)) {
      return <span>{value.join('、')}</span>;
    }
    return (
      <div className={depth > 0 ? 'ml-3' : ''}>
        {value.map((item, i) => (
          <div key={i} className="flex items-start gap-1.5 py-0.5">
            <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-gray-400" />
            <span className="min-w-0">{renderValue(item, depth + 1)}</span>
          </div>
        ))}
      </div>
    );
  }
  if (typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>);
    if (entries.length === 0) return <span className="text-gray-400">(空)</span>;
    return (
      <div
        className={cn(
          depth > 0
            ? 'ml-3 border-l-2 border-gray-200 pl-2 dark:border-gray-600'
            : '',
        )}
      >
        {entries.map(([k, v]) => (
          <div key={k} className="py-0.5">
            <span className="font-medium text-gray-600 dark:text-gray-300">
              {translateKey(k)}
            </span>
            {typeof v === 'object' && v !== null && !Array.isArray(v) ? (
              <div className="mt-0.5">{renderValue(v, depth + 1)}</div>
            ) : Array.isArray(v) && v.length > 3 ? (
              <div className="mt-0.5">{renderValue(v, depth + 1)}</div>
            ) : (
              <span>: {renderValue(v, depth + 1)}</span>
            )}
          </div>
        ))}
      </div>
    );
  }
  return String(value);
}

/* ── Step row ──────────────────────────────────────────────── */

function StepRow({
  step,
  isActive,
  showBorder,
}: {
  step: ThinkingStep;
  isActive: boolean;
  showBorder: boolean;
}) {
  const [open, setOpen] = useState(true);
  const isRunning = step.status === 'running';

  let parsed: unknown;
  try {
    parsed = JSON.parse(step.content);
  } catch {
    parsed = step.content;
  }

  return (
    <div
      className={cn(
        'px-3 py-2',
        showBorder && 'border-b border-gray-100 dark:border-gray-700',
      )}
    >
      <button
        onClick={() => !isRunning && setOpen((v) => !v)}
        className="flex w-full items-center gap-2 text-xs"
      >
        {isRunning ? (
          <span className="relative inline-flex h-1.5 w-4 items-center">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary-400 opacity-75" />
            <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-primary-400" />
          </span>
        ) : (
          <span
            className={cn(
              'inline-block h-1.5 w-1.5 rounded-full',
              isActive
                ? 'bg-primary-400 animate-pulse'
                : 'bg-green-400',
            )}
          />
        )}
        <span className="font-medium text-gray-600 dark:text-gray-300">
          {step.label || step.step}
        </span>
        {!isRunning && (
          <span className="ml-auto text-gray-400">
            {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          </span>
        )}
      </button>
      {isRunning && (
        <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
          <div className="h-full animate-progress rounded-full bg-gradient-to-r from-primary-400 to-primary-500 bg-[length:200%_100%]" />
        </div>
      )}
      {!isRunning && open && (
        <div className="mt-1.5 text-xs leading-relaxed text-gray-600 dark:text-gray-400">
          {renderValue(parsed)}
        </div>
      )}
    </div>
  );
}

/* ── Main component ────────────────────────────────────────── */

interface ThinkingViewProps {
  steps: ThinkingStep[];
}

export function ThinkingView({ steps }: ThinkingViewProps) {
  const [expanded, setExpanded] = useState(true);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (expanded && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [steps.length, expanded]);

  if (steps.length === 0) return null;

  return (
    <div>
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center gap-1.5 rounded-md px-1 py-1 text-xs text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300"
      >
        <Cpu size={13} className="text-gray-400" />
        <span className="font-medium">思考过程</span>
        <span className="ml-auto">
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </span>
      </button>

      {expanded && (
        <div
          ref={containerRef}
          className="mt-1 max-h-72 overflow-y-auto rounded-lg border border-gray-100 bg-gray-50/80 dark:border-gray-700 dark:bg-gray-900/40"
        >
          {steps.map((step, idx) => (
            <StepRow
              key={idx}
              step={step}
              isActive={idx === steps.length - 1}
              showBorder={idx < steps.length - 1}
            />
          ))}
        </div>
      )}
    </div>
  );
}
