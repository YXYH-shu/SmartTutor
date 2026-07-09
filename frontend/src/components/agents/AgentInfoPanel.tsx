import { X, Cpu } from 'lucide-react';
import { useUIStore } from '@/stores/uiStore';
import { AgentStudio } from './AgentStudio';
import { AgentDetailDrawer } from './AgentDetailDrawer';

/**
 * AgentInfoPanel
 *
 * 外层折叠容器 + Header + 三段式主体(AgentStudio)。
 * 删除原 agent 下拉(失效:AgentStudio 不读 uiStore.selectedAgent)。
 * 点击任何 agent 卡片写入 chatStore.selectedDetailAgent,
 * 触发 AgentDetailDrawer 在右栏内浮层覆盖。
 *
 * 外层 div 加 relative,让抽屉 absolute inset-0 相对它定位。
 */
export function AgentInfoPanel() {
  const setRightPanelOpen = useUIStore((s) => s.setRightPanelOpen);
  const close = () => setRightPanelOpen(false);

  return (
    <div className="relative flex h-full w-80 flex-col border-l border-border-subtle bg-bg-base animate-slide-in-right">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3">
        <div className="flex items-center gap-2">
          <Cpu size={16} className="text-text-secondary" />
          <h2 className="text-14 font-display font-semibold text-text-primary">
            智能体工作室
          </h2>
        </div>
        <button
          type="button"
          onClick={close}
          className="rounded-md p-1 text-text-tertiary transition-all duration-200 hover:bg-bg-elevated hover:text-text-primary"
        >
          <X size={16} />
        </button>
      </div>

      {/* 三段式主体 */}
      <div className="flex-1 overflow-hidden">
        <AgentStudio />
      </div>

      {/* 详情抽屉(absolute 覆盖整个右栏,selectedDetailAgent 为 null 时不渲染) */}
      <AgentDetailDrawer />
    </div>
  );
}

export default AgentInfoPanel;
