/**
 * SessionThumbnail
 *
 * 左栏会话列表项的内部视觉单元。上行圆点线(4-8 个知识节点缩略),
 * 下行会话标题 + 相对时间。
 *
 * 数据来源(后端 task 7 后):
 *   - 优先读 conversation.knowledge_points(后端返回的 KnowledgeNodeSummary[])
 *   - 旧会话该字段为 null / 空数组 → 降级到 MOCK_NODES,保持视觉一致
 *
 * 重点节点位置:
 *   - 有真实节点时,优先取 mastery < 0.4 的弱点节点
 *   - 全是 mock 时用确定性策略避免刷新抖动:
 *       highlightIdx = (title.length + id.length) % nodes.length
 *
 * 列表项外层 <li> 和点击/重命名/删除交互由父组件(Sidebar.tsx)保留,
 * 这里只渲染内容 JSX。
 */

import { cn } from '@/utils/cn';
import type { Conversation, KnowledgeNode } from '@/types';

export interface SessionThumbnailProps {
  conversation: Conversation;
  isActive: boolean;
  onClick?: () => void;
}

/* mock 节点(后端补字段前用),共 5 个 */
const MOCK_NODES: KnowledgeNode[] = [
  { id: 'm1', label: '代数', isHighlight: false },
  { id: 'm2', label: '函数', isHighlight: false },
  { id: 'm3', label: '几何', isHighlight: false },
  { id: 'm4', label: '概率', isHighlight: false },
  { id: 'm5', label: '统计', isHighlight: false },
];

function relativeTime(iso: string): string {
  const t = new Date(iso).getTime();
  if (!t) return '';
  const diff = Date.now() - t;
  const m = Math.floor(diff / 60000);
  if (m < 1) return '刚刚';
  if (m < 60) return `${m} 分钟前`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} 小时前`;
  const d = Math.floor(h / 24);
  if (d < 7) return `${d} 天前`;
  return new Date(iso).toLocaleDateString();
}

/**
 * 计算重点节点下标。
 * 真实数据优先取 mastery < 0.4 的弱点;无弱点时取第一个节点(若有 highlight_agent)
 * 或不强标(若无)。mock 数据走确定性策略。
 */
function computeHighlightIdx(
  nodes: KnowledgeNode[],
  hasRealData: boolean,
  hasHighlightAgent: boolean,
  conversation: Conversation,
): number {
  if (nodes.length === 0) return -1;
  if (hasRealData) {
    const weakIdx = nodes.findIndex(
      (n) => typeof n.mastery === 'number' && n.mastery < 0.4,
    );
    if (weakIdx >= 0) return weakIdx;
    // 无弱点:有 highlight_agent 时仍标第一个,否则不强标
    return hasHighlightAgent ? 0 : -1;
  }
  // mock 模式:确定性,避免刷新抖动
  // 修复原代码运算符优先级 bug:`?? 0 + x` 会被解析成 `?? (0 + x)`
  const titleLen = conversation.title?.length ?? 0;
  const idLen = conversation.id.length;
  return (titleLen + idLen) % nodes.length;
}

export function SessionThumbnail({
  conversation,
  isActive,
}: SessionThumbnailProps) {
  // 优先用真实 knowledge_points,空时降级 mock
  const realNodes = conversation.knowledge_points ?? [];
  const nodes = realNodes.length > 0 ? realNodes : MOCK_NODES;
  const hasRealData = realNodes.length > 0;
  const hasHighlightAgent = Boolean(conversation.highlight_agent);

  const highlightIdx = computeHighlightIdx(
    nodes,
    hasRealData,
    hasHighlightAgent,
    conversation,
  );

  const title = (conversation.title || '新对话').slice(0, 20);
  const ts = relativeTime(conversation.updated_at || conversation.created_at);

  return (
    <div className="flex w-full flex-col gap-1.5 py-1">
      {/* 上行:圆点线 */}
      <div className="flex items-center">
        <svg
          width="100%"
          height="8"
          viewBox="0 0 120 8"
          preserveAspectRatio="none"
          className="overflow-visible"
          aria-hidden
        >
          {nodes.slice(0, 6).map((n, i) => {
            const x = 6 + i * 18;
            const isHi = i === highlightIdx;
            return (
              <g key={n.id}>
                {i > 0 && (
                  <line
                    x1={6 + (i - 1) * 18 + 3}
                    y1={4}
                    x2={x - 3}
                    y2={4}
                    stroke="currentColor"
                    strokeWidth={0.5}
                    strokeDasharray="2 2"
                    className="text-text-tertiary opacity-60"
                  />
                )}
                <circle
                  cx={x}
                  cy={4}
                  r={isHi ? 4 : 3}
                  className={isHi ? 'text-accent' : 'text-text-tertiary'}
                  fill="currentColor"
                  style={
                    isHi
                      ? { filter: 'drop-shadow(0 0 4px var(--color-accent-glow))' }
                      : undefined
                  }
                />
              </g>
            );
          })}
        </svg>
      </div>

      {/* 下行:标题 + 时间 */}
      <div className="flex flex-col leading-tight">
        <span
          className={cn(
            'truncate text-14 font-medium',
            isActive ? 'text-text-primary' : 'text-text-secondary',
          )}
        >
          {title}
        </span>
        {ts && (
          <span className="truncate text-12 text-text-tertiary font-mono">{ts}</span>
        )}
      </div>
    </div>
  );
}
