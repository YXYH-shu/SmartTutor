import { Menu, Moon, Sun, Cpu } from 'lucide-react';
import { useUIStore } from '@/stores/uiStore';
import { useChatStore } from '@/stores/chatStore';

export function Header() {
  const { theme, setTheme, toggleSidebar, rightPanelOpen, toggleRightPanel } = useUIStore();
  const { conversations, currentConversationId } = useChatStore();

  const currentConv = conversations.find((c) => c.id === currentConversationId);

  return (
    <header className="relative flex h-14 items-center gap-3 border-b border-white/[0.06] bg-[#0f0f13]/80 backdrop-blur-xl px-4 animate-fade-in">
      <button
        onClick={toggleSidebar}
        className="rounded-lg p-1.5 text-gray-400 hover:text-white hover:bg-white/[0.06] transition-all duration-200"
      >
        <Menu size={18} />
      </button>

      <h1 className="flex-1 truncate text-sm font-semibold tracking-tight text-white">
        {currentConv?.title || '智慧导师'}
      </h1>

      <button
        onClick={toggleRightPanel}
        className={`hidden rounded-lg p-2 transition-all duration-200 lg:block ${
          rightPanelOpen
            ? 'bg-primary-500/10 text-primary-400 ring-1 ring-primary-500/20'
            : 'text-gray-400 hover:text-white hover:bg-white/[0.06]'
        }`}
      >
        <Cpu size={16} />
      </button>

      <button
        onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}
        className="rounded-lg p-2 text-gray-400 hover:text-white hover:bg-white/[0.06] transition-all duration-200"
      >
        {theme === 'light' ? <Moon size={16} /> : <Sun size={16} />}
      </button>
    </header>
  );
}
