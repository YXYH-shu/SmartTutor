/**
 * CognitiveMapDrawer
 *
 * 右下角悬浮按钮 + 全屏抽屉,显示本轮探测轨迹的认知地图。
 *
 * 数据来源(三层):
 *   1. 用户级 KG: GET /api/v1/users/knowledge-graph(kgService 拉取,抽屉首次打开加载)
 *   2. 本轮 touched: chatStore.currentTouchedNodes(前景层,合并到 KG 之上)
 *   3. mock fallback: KG + 本轮都为空时,显示 MOCK_NODES 供预览
 *
 * 边:
 *   - KG 真实 edges(优先)
 *   - 空 → mock(中心 → 各子节点,layoutNodes 自动补)
 *
 * 轨迹动画: chatStore.currentTurn.trajectory(kp_id 顺序);空时不画路径动画
 *
 * 抽屉打开时锁 body scroll,关闭时还原。
 * 不引入新 npm 包,SVG 手画固定环形布局(中心节点 + 环形子节点)。
 */

import { useEffect, useMemo, useState } from 'react';
import { Network, X, Play } from 'lucide-react';
import { useChatStore } from '@/stores/chatStore';
import { cn } from '@/utils/cn';
import type { KnowledgeNode } from '@/types';
import kgService, {
  type KnowledgeGraphData,
  type KnowledgeGraphEdge,
} from '@/services/kg.service';

// 模块级空数组常量,避免 selector 用 ?? [] 每次创建新引用导致 useSyncExternalStore 死循环
const EMPTY_TRAJECTORY: string[] = [];

const MOCK_NODES: KnowledgeNode[] = [
  { id: 'root', label: '本轮主题', isHighlight: false },
  { id: 'n1', label: '知识点 A', isHighlight: false },
  { id: 'n2', label: '知识点 B', isHighlight: true },
  { id: 'n3', label: '知识点 C', isHighlight: false },
  { id: 'n4', label: '知识点 D', isHighlight: false },
  { id: 'n5', label: '知识点 E', isHighlight: false },
  { id: 'n6', label: '知识点 F', isHighlight: false },
];

interface LayoutNode {
  id: string;
  label: string;
  x: number;
  y: number;
  isHighlight?: boolean;
  isCenter: boolean;
}

interface LayoutEdge {
  from: string;
  to: string;
}

function layoutNodes(
  nodes: KnowledgeNode[],
  edges: KnowledgeGraphEdge[],
): { nodes: LayoutNode[]; edges: LayoutEdge[] } {
  // 第一个节点作为中心,其余环形排列
  if (nodes.length === 0) {
    return { nodes: [], edges: [] };
  }
  const cx = 250;
  const cy = 200;
  const r = 130;
  const laid: LayoutNode[] = nodes.map((n, i) => {
    if (i === 0) {
      return { ...n, x: cx, y: cy, isCenter: true };
    }
    // 其余在半径 r 上均匀分布
    const angle = ((i - 1) / Math.max(nodes.length - 1, 1)) * Math.PI * 2 - Math.PI / 2;
    return {
      ...n,
      x: cx + r * Math.cos(angle),
      y: cy + r * Math.sin(angle),
      isCenter: false,
    };
  });
  // 真实 edges 优先;空时 mock 中心 → 各子节点
  const layoutEdges: LayoutEdge[] =
    edges.length > 0
      ? edges.map((e) => ({ from: e.source, to: e.target }))
      : laid.filter((n) => !n.isCenter).map((n) => ({ from: laid[0].id, to: n.id }));
  return { nodes: laid, edges: layoutEdges };
}

function FAB() {
  return (
    <button
      type="button"
      aria-label="打开认知地图"
      className={cn(
        'fixed bottom-6 right-6 z-40 flex h-12 w-12 items-center justify-center rounded-full',
        'border border-border-subtle bg-bg-elevated shadow-3 transition-transform duration-200 ease-spring',
        'hover:scale-105',
      )}
    >
      <Network size={20} className="text-accent" />
    </button>
  );
}

export function CognitiveMapDrawer() {
  const [open, setOpen] = useState(false);
  const [replayKey, setReplayKey] = useState(0);
  const touchedNodes = useChatStore((s) => s.currentTouchedNodes);
  const trajectory = useChatStore((s) => s.currentTurn?.trajectory ?? EMPTY_TRAJECTORY);

  // 用户级 KG 数据(抽屉首次打开时加载,不重复)
  const [kgData, setKgData] = useState<KnowledgeGraphData | null>(null);
  const [kgError, setKgError] = useState<boolean>(false);

  // 锁滚动
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  // 首次打开加载 KG
  useEffect(() => {
    if (!open || kgData || kgError) return;
    let cancelled = false;
    kgService
      .getUserKnowledgeGraph()
      .then((data) => {
        if (!cancelled) setKgData(data);
      })
      .catch(() => {
        if (!cancelled) setKgError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [open, kgData, kgError]);

  // 三层数据合并:KG 背景层 + 本轮 touched 前景层 + mock fallback
  const renderData = useMemo<{
    nodes: KnowledgeNode[];
    edges: KnowledgeGraphEdge[];
    isMock: boolean;
  }>(() => {
    const kgNodes = kgData?.nodes ?? [];
    const touchedIds = new Set(touchedNodes.map((n) => n.id));
    // KG 已有节点:isHighlight 同时考虑 mastery<0.4 和是否本轮 touched
    const mergedKg = kgNodes.map((n) => ({
      ...n,
      isHighlight: n.isHighlight || touchedIds.has(n.id),
    }));
    // 本轮 touched 但 KG 里没有的:追加到末尾
    const touchedNotInKg = touchedNodes.filter((n) => !kgNodes.some((k) => k.id === n.id));
    const merged = [...mergedKg, ...touchedNotInKg];

    if (merged.length === 0) {
      return { nodes: MOCK_NODES, edges: [], isMock: true };
    }
    return {
      nodes: merged,
      edges: kgData?.edges ?? [],
      isMock: false,
    };
  }, [kgData, touchedNodes]);

  const { nodes: laidNodes, edges } = useMemo(
    () => layoutNodes(renderData.nodes, renderData.edges),
    [renderData],
  );

  // 轨迹映射到节点 id 序列(只保留 trajectory 里出现的节点)
  const trajectoryIds =
    trajectory && trajectory.length > 0
      ? trajectory
      : []; // 空时不画路径动画

  const replayDuration =
    (typeof window !== 'undefined' &&
      getComputedStyle(document.documentElement).getPropertyValue('--duration-flow')) ||
    '800ms';
  const totalPathLen = trajectoryIds.length * 80; // 粗略估计每段 80px

  return (
    <>
      <button
        type="button"
        aria-label="打开认知地图"
        onClick={() => setOpen(true)}
        className={cn(
          'fixed bottom-6 right-6 z-40 flex h-12 w-12 items-center justify-center rounded-full',
          'border border-border-subtle bg-bg-elevated shadow-3 transition-transform duration-200 ease-spring',
          'hover:scale-105',
        )}
      >
        <Network size={20} className="text-accent" />
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex flex-col bg-bg-base/95 backdrop-blur-24 animate-fade-in">
          {/* Header */}
          <header className="flex items-center justify-between border-b border-border-subtle px-6 py-4">
            <div className="flex items-center gap-3">
              <Network size={20} className="text-accent" />
              <h2 className="text-18 font-display font-semibold text-text-primary">
                认知地图 · 本轮探测轨迹
              </h2>
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              aria-label="关闭"
              className="rounded-md p-1.5 text-text-tertiary hover:bg-bg-elevated hover:text-text-primary transition-colors"
            >
              <X size={18} />
            </button>
          </header>

          {/* SVG 主体 */}
          <main className="relative flex-1 overflow-hidden">
            <svg
              viewBox="0 0 500 400"
              preserveAspectRatio="xMidYMid meet"
              className="h-full w-full"
            >
              {/* 边 */}
              {edges.map((e, i) => {
                const from = laidNodes.find((n) => n.id === e.from);
                const to = laidNodes.find((n) => n.id === e.to);
                if (!from || !to) return null;
                // 边是否在轨迹上(连续 trajectory 中相邻且匹配)
                const inTraj = trajectoryIds.some((id, idx) => {
                  const next = trajectoryIds[idx + 1];
                  return (
                    (id === e.from && next === e.to) ||
                    (id === e.to && next === e.from)
                  );
                });
                return (
                  <line
                    key={i}
                    x1={from.x}
                    y1={from.y}
                    x2={to.x}
                    y2={to.y}
                    stroke={inTraj ? 'var(--color-accent)' : 'var(--color-border-subtle)'}
                    strokeWidth={inTraj ? 1.5 : 1}
                    strokeOpacity={inTraj ? 0.9 : 0.6}
                  />
                );
              })}

              {/* 重播轨迹路径动画(基于 trajectoryIds 顺序串联) */}
              {trajectoryIds.length >= 2 && (
                <g key={replayKey}>
                  {trajectoryIds.slice(0, -1).map((id, i) => {
                    const from = laidNodes.find((n) => n.id === id);
                    const to = laidNodes.find((n) => n.id === trajectoryIds[i + 1]);
                    if (!from || !to) return null;
                    return (
                      <line
                        key={i}
                        x1={from.x}
                        y1={from.y}
                        x2={to.x}
                        y2={to.y}
                        stroke="var(--color-accent)"
                        strokeWidth={2.5}
                        strokeDasharray={totalPathLen}
                        strokeDashoffset={totalPathLen}
                        style={{
                          animation: `flow-stroke ${replayDuration} ${i * 200}ms linear forwards`,
                          ['--flow-len' as string]: totalPathLen,
                        }}
                      />
                    );
                  })}
                </g>
              )}

              {/* 节点 */}
              {laidNodes.map((n) => (
                <g key={n.id}>
                  {/* 重点节点双圈 */}
                  {n.isHighlight && (
                    <circle
                      cx={n.x}
                      cy={n.y}
                      r={n.isCenter ? 26 : 18}
                      fill="none"
                      stroke="var(--color-accent)"
                      strokeWidth={3}
                      strokeOpacity={0.3}
                    />
                  )}
                  <circle
                    cx={n.x}
                    cy={n.y}
                    r={n.isCenter ? 22 : 14}
                    fill={n.isHighlight ? 'var(--color-accent-soft)' : 'none'}
                    stroke={n.isHighlight ? 'var(--color-accent)' : 'var(--color-text-secondary)'}
                    strokeWidth={1.5}
                  />
                  <text
                    x={n.x}
                    y={n.y + (n.isCenter ? 38 : 28)}
                    textAnchor="middle"
                    fontSize={11}
                    fill={n.isHighlight ? 'var(--color-accent)' : 'var(--color-text-secondary)'}
                    fontFamily="var(--font-body)"
                  >
                    {n.label}
                  </text>
                </g>
              ))}
            </svg>

            {/* 数据状态提示条 */}
            {kgError && (
              <div className="pointer-events-none absolute bottom-4 left-1/2 -translate-x-1/2 rounded-md border border-border-subtle bg-bg-elevated px-3 py-1.5 text-12 text-text-tertiary">
                知识图谱加载失败,显示 mock 数据
              </div>
            )}
            {!kgError && renderData.isMock && (
              <div className="pointer-events-none absolute bottom-4 left-1/2 -translate-x-1/2 rounded-md border border-border-subtle bg-bg-elevated px-3 py-1.5 text-12 text-text-tertiary">
                当前用户暂无知识图谱数据,显示 mock 节点供预览
              </div>
            )}
            {!kgError && !renderData.isMock && (kgData?.nodes.length ?? 0) === 0 && (
              <div className="pointer-events-none absolute bottom-4 left-1/2 -translate-x-1/2 rounded-md border border-border-subtle bg-bg-elevated px-3 py-1.5 text-12 text-text-tertiary">
                本轮暂无轨迹数据
              </div>
            )}
          </main>

          {/* Footer 重播按钮 */}
          <footer className="flex items-center justify-between border-t border-border-subtle px-6 py-3">
            <p className="text-12 text-text-tertiary">
              {trajectoryIds.length > 0
                ? `本轮轨迹: ${trajectoryIds.length} 个节点`
                : '本轮暂无轨迹'}
            </p>
            <button
              type="button"
              onClick={() => setReplayKey((k) => k + 1)}
              disabled={trajectoryIds.length < 2}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-14 transition-colors',
                trajectoryIds.length < 2
                  ? 'cursor-not-allowed bg-bg-elevated text-text-tertiary'
                  : 'bg-accent-soft text-accent hover:bg-accent hover:text-bg-base',
              )}
            >
              <Play size={14} />
              重播轨迹
            </button>
          </footer>
        </div>
      )}
    </>
  );
}

export default CognitiveMapDrawer;

// 保留 FAB 命名导出供测试引用
void FAB;
