/**
 * CognitivePathBar
 *
 * 中栏顶部一条 32px 的横向知识路径,显示本轮触及的节点(普通 + 重点 + active)。
 *
 * 数据来源: chatStore.currentTouchedNodes
 * - 为空时整组件 return null(不占空间)
 *
 * 呼吸光晕互斥(全局唯一活跃):
 *   - 当 chatStore.activeNodeId === node.id 时,该节点呼吸
 *   - 此时 AgentStudio Hero Slot 的呼吸动画条件 = !activeNodeId,自动停止
 *
 * 节点上限: 12 个。超过时显示首末 + "...",middle truncated。
 * 窗口 < 640px: 只显示首末 + "..."。
 */

import { useChatStore } from '@/stores/chatStore';
import { cn } from '@/utils/cn';
import type { KnowledgeNode } from '@/types';

const MAX_NODES = 12;

function NodeDot({
  node,
  isActive,
  isHighlight,
}: {
  node: KnowledgeNode;
  isActive: boolean;
  isHighlight: boolean;
}) {
  return (
    <div
      className="group relative flex items-center"
      title={node.label + (isHighlight ? ' (本轮重点)' : '')}
    >
      <span
        className={cn(
          'inline-block rounded-full transition-all duration-200',
          isHighlight ? 'h-2 w-2 text-accent' : 'h-2 w-2 text-text-secondary',
          isActive && 'animate-breathe text-accent',
        )}
        style={{
          backgroundColor: 'currentColor',
          filter:
            isHighlight || isActive
              ? 'drop-shadow(0 0 8px var(--color-accent-glow))'
              : undefined,
        }}
      />
      {/* hover tooltip */}
      <span className="pointer-events-none absolute -top-7 left-1/2 z-10 -translate-x-1/2 whitespace-nowrap rounded-md border border-border-subtle bg-bg-elevated px-2 py-0.5 text-12 text-text-primary opacity-0 shadow-2 transition-opacity duration-200 group-hover:opacity-100">
        {node.label}
      </span>
    </div>
  );
}

function Connector() {
  return (
    <svg width="6" height="2" aria-hidden className="text-text-tertiary opacity-50">
      <line
        x1={0}
        y1={1}
        x2={6}
        y2={1}
        stroke="currentColor"
        strokeWidth={0.5}
        strokeDasharray="2 2"
      />
    </svg>
  );
}

export function CognitivePathBar() {
  const nodes = useChatStore((s) => s.currentTouchedNodes);
  const activeNodeId = useChatStore((s) => s.activeNodeId);
  const setActiveNode = useChatStore((s) => s.setActiveNode);

  // 数据为空时整组件不渲染
  if (!nodes || nodes.length === 0) return null;

  // 计算显示节点列表(超过 12 截断中间)
  let display: KnowledgeNode[] = nodes.slice(0, MAX_NODES);
  let middleTruncated = false;
  if (nodes.length > MAX_NODES) {
    const head = nodes.slice(0, 5);
    const tail = nodes.slice(nodes.length - 5);
    display = [...head, ...tail];
    middleTruncated = true;
  }

  return (
    <div className="sticky top-0 z-10 flex h-8 items-center gap-2 border-b border-border-subtle bg-bg-base px-4">
      <div className="hidden items-center gap-2 sm:flex">
        {display.map((n, i) => {
          const realIdx = i; // display 中的位置
          const isActive = !!activeNodeId && n.id === activeNodeId;
          const isHighlight = !!n.isHighlight;
          return (
            <div key={`${n.id}-${realIdx}`} className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setActiveNode(isActive ? undefined : n.id)}
                className="flex items-center"
                aria-label={`知识点: ${n.label}`}
              >
                <NodeDot node={n} isActive={isActive} isHighlight={isHighlight} />
              </button>
              {/* 在中间或末尾插入连接线 */}
              {i < display.length - 1 && (
                <>
                  {middleTruncated && i === 4 ? (
                    <span className="text-12 text-text-tertiary">…</span>
                  ) : null}
                  <Connector />
                </>
              )}
            </div>
          );
        })}
      </div>

      {/* 窄屏:只显示首末 + ... */}
      <div className="flex items-center gap-2 sm:hidden">
        <NodeDot
          node={nodes[0]}
          isActive={!!activeNodeId && nodes[0].id === activeNodeId}
          isHighlight={!!nodes[0].isHighlight}
        />
        <span className="text-12 text-text-tertiary">…</span>
        {nodes.length > 1 && (
          <NodeDot
            node={nodes[nodes.length - 1]}
            isActive={
              !!activeNodeId && nodes[nodes.length - 1].id === activeNodeId
            }
            isHighlight={!!nodes[nodes.length - 1].isHighlight}
          />
        )}
      </div>
    </div>
  );
}
