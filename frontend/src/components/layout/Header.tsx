import { Menu, Moon, Sun, Cpu } from 'lucide-react';
import { useUIStore } from '@/stores/uiStore';
import { useChatStore } from '@/stores/chatStore';

export function Header() {
  const { theme, setTheme, toggleSidebar, rightPanelOpen, toggleRightPanel } = useUIStore();
  const { conversations, currentConversationId } = useChatStore();

  const currentConv = conversations.find((c) => c.id === currentConversationId);

  return (
    <header className="relative flex h-14 items-center gap-3 border-b border-border-subtle bg-bg-base/80 backdrop-blur-xl px-4 animate-fade-in">
      <button
        onClick={toggleSidebar}
        className="rounded-lg p-1.5 text-text-secondary hover:text-text-primary hover:bg-bg-elevated/50 transition-all duration-200"
      >
        <Menu size={18} />
      </button>

      <h1 className="font-display flex-1 truncate text-14 font-semibold tracking-tight text-text-primary">
        {currentConv?.title || '智慧导师'}
      </h1>

      <button
        onClick={toggleRightPanel}
        className={`rounded-lg p-2 transition-all duration-200 ${
          rightPanelOpen
            ? 'bg-accent-soft text-accent ring-1 ring-accent/20'
            : 'text-text-secondary hover:text-text-primary hover:bg-bg-elevated/50'
        }`}
      >
        <Cpu size={16} />
      </button>

      <button
        onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}
        className="rounded-lg p-2 text-text-secondary hover:text-text-primary hover:bg-bg-elevated/50 transition-all duration-200"
      >
        {theme === 'light' ? <Moon size={16} /> : <Sun size={16} />}
      </button>
    </header>
  );
}
