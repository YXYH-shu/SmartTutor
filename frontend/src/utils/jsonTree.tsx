import { cn } from '@/utils/cn';

/* ── Key name translation ──────────────────────────────────── */

export const KEY_LABELS: Record<string, string> = {
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

export function renderValue(value: unknown, depth = 0): React.ReactNode {
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
