import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface UIState {
  sidebarOpen: boolean;
  theme: 'light' | 'dark';
  rightPanelOpen: boolean;
  selectedAgent: string;
  toggleSidebar: () => void;
  setSidebarOpen: (v: boolean) => void;
  setTheme: (t: 'light' | 'dark') => void;
  toggleRightPanel: () => void;
  setRightPanelOpen: (v: boolean) => void;
  setSelectedAgent: (agent: string) => void;
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      sidebarOpen: true,
      theme: 'light',
      rightPanelOpen: false,
      selectedAgent: 'emotion_analyzer',

      toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
      setSidebarOpen: (sidebarOpen) => set({ sidebarOpen }),
      setTheme: (theme) => {
        document.documentElement.classList.toggle('dark', theme === 'dark');
        set({ theme });
      },
      toggleRightPanel: () => set((s) => ({ rightPanelOpen: !s.rightPanelOpen })),
      setRightPanelOpen: (rightPanelOpen) => set({ rightPanelOpen }),
      setSelectedAgent: (selectedAgent) => set({ selectedAgent }),
    }),
    { name: 'smart-tutor-ui', partialize: (s) => ({ theme: s.theme }) },
  ),
);
