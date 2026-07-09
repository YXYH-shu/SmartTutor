import { Outlet, useLocation } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { AgentInfoPanel } from '@/components/agents/AgentInfoPanel';
import { CognitivePathBar } from '@/components/chat/CognitivePathBar';
import { CognitiveMapDrawer } from '@/components/cognitive/CognitiveMapDrawer';
import { useUIStore } from '@/stores/uiStore';

export function MainLayout() {
  const { sidebarOpen, rightPanelOpen } = useUIStore();
  const location = useLocation();
  // Path Bar 仅在 chat 路由下出现(KT 诊断等独立页不显示);数据为空时组件自己 return null
  const showPathBar = location.pathname.startsWith('/dashboard/chat');

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
        className={`shrink-0 transition-all duration-500 ease-out ${
          rightPanelOpen ? 'w-80' : 'w-0'
        } overflow-hidden`}
      >
        <AgentInfoPanel />
      </div>

      {/* 全局浮层:认知地图抽屉(右下角悬浮按钮 + 全屏抽屉) */}
      <CognitiveMapDrawer />
    </div>
  );
}
