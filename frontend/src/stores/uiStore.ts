import { create } from 'zustand';
import { persist } from 'zustand/middleware';

type Theme = 'light' | 'dark';

interface UIState {
  sidebarOpen: boolean;
  theme: Theme;
  rightPanelOpen: boolean;
  selectedAgent: string;
  toggleSidebar: () => void;
  setSidebarOpen: (v: boolean) => void;
  setTheme: (t: Theme) => void;
  toggleRightPanel: () => void;
  setRightPanelOpen: (v: boolean) => void;
  setSelectedAgent: (agent: string) => void;
}

/**
 * 把 theme 应用到 <html> 上：
 * - data-theme 属性驱动 tokens.css 里的 CSS 变量
 * - .dark class 保留向后兼容（部分旧 className 仍读 dark: variant）
 */
export const applyTheme = (theme: Theme) => {
  if (typeof document === 'undefined') return;
  const root = document.documentElement;
  root.dataset.theme = theme;
  root.classList.toggle('dark', theme === 'dark');
  try {
    localStorage.setItem('theme', theme);
  } catch {
    /* localStorage 不可用时静默忽略 */
  }
};

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      sidebarOpen: true,
      theme: 'dark',
      rightPanelOpen: false,
      selectedAgent: 'emotion_analyzer',

      toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
      setSidebarOpen: (sidebarOpen) => set({ sidebarOpen }),
      setTheme: (theme) => {
        applyTheme(theme);
        set({ theme });
      },
      toggleRightPanel: () => set((s) => ({ rightPanelOpen: !s.rightPanelOpen })),
      setRightPanelOpen: (rightPanelOpen) => set({ rightPanelOpen }),
      setSelectedAgent: (selectedAgent) => set({ selectedAgent }),
    }),
    {
      name: 'smart-tutor-ui',
      partialize: (s) => ({ theme: s.theme }),
      // rehydrate 之后把 theme 同步到 DOM，避免刷新后 token 未应用
      onRehydrateStorage: () => (state) => {
        if (state?.theme) applyTheme(state.theme);
      },
    },
  ),
);
