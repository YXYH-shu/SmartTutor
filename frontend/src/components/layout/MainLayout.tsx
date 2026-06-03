import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { AgentInfoPanel } from '@/components/agents/AgentInfoPanel';
import { useUIStore } from '@/stores/uiStore';

export function MainLayout() {
  const { sidebarOpen, rightPanelOpen } = useUIStore();

  return (
    <div className="flex h-screen overflow-hidden bg-premium animate-fade-in">
      <div
        className={`shrink-0 transition-all duration-500 ease-out ${
          sidebarOpen ? 'w-64' : 'w-0'
        } overflow-hidden`}
      >
        <Sidebar />
      </div>

      <div className="flex flex-1 flex-col overflow-hidden">
        <Header />
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
    </div>
  );
}
