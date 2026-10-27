import { Outlet, useLocation } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { AgentInfoPanel } from '@/components/agents/AgentInfoPanel';
import { CognitivePathBar } from '@/components/chat/CognitivePathBar';
import { CognitiveMapDrawer } from '@/components/cognitive/CognitiveMapDrawer';
import { useUIStore } from '@/stores/uiStore';

const RIGHT_PANEL_MIN = 280;
const RIGHT_PANEL_MAX = 560;

export function MainLayout() {
  const {
    sidebarOpen,
    rightPanelOpen,
    rightPanelWidth,
    isResizingRightPanel,
    setRightPanelWidth,
    setResizingRightPanel,
  } = useUIStore();
  const location = useLocation();
  // Path Bar 仅在 chat 路由下出现(KT 诊断等独立页不显示);数据为空时组件自己 return null
  const showPathBar = location.pathname.startsWith('/dashboard/chat');

  const startResize = (e: React.PointerEvent<HTMLDivElement>) => {
    e.preventDefault();
    setResizingRightPanel(true);
    const onMove = (ev: PointerEvent) => {
      const width = Math.min(RIGHT_PANEL_MAX, Math.max(RIGHT_PANEL_MIN, window.innerWidth - ev.clientX));
      setRightPanelWidth(width);
    };
    const onUp = () => {
      setResizingRightPanel(false);
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  };

  return (
    <div className="flex h-screen overflow-hidden bg-premium animate-fade-in text-text-primary">
      <div
        className={`shrink-0 transition-all duration-500 ease-out ${
          sidebarOpen ? 'w-64' : 'w-0'
        } overflow-hidden`}
      >
        <Sidebar />
      </div>

      <div className="flex flex-1 flex-col overflow-hidden">
        <Header />
        {showPathBar && <CognitivePathBar />}
        <main className="flex-1 overflow-hidden">
          <Outlet />
        </main>
      </div>

      <div
        className={`relative shrink-0 overflow-hidden ${
          isResizingRightPanel ? 'select-none' : ''
        } ${
          rightPanelOpen && !isResizingRightPanel
            ? 'transition-all duration-500 ease-out'
            : ''
        }`}
        style={{ width: rightPanelOpen ? rightPanelWidth : 0 }}
      >
        {rightPanelOpen && (
          <div
            onPointerDown={startResize}
            className="absolute left-0 top-0 z-40 h-full w-1.5 cursor-col-resize transition-colors hover:bg-accent/40"
            title="拖拽调整宽度"
            aria-label="拖拽调整智能体工作室宽度"
          />
        )}
        <AgentInfoPanel />
      </div>

      {/* 全局浮层:认知地图抽屉(右下角悬浮按钮 + 全屏抽屉) */}
      <CognitiveMapDrawer />
    </div>
  );
}
