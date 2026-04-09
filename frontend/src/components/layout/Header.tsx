import { Menu, Moon, Sun } from 'lucide-react';
import { useUIStore } from '@/stores/uiStore';
import { useChatStore } from '@/stores/chatStore';

export function Header() {
  const { theme, setTheme, toggleSidebar } = useUIStore();
  const { conversations, currentConversationId } = useChatStore();

  const currentConv = conversations.find((c) => c.id === currentConversationId);

  return (
    <header className="flex h-14 items-center gap-3 border-b border-gray-200 bg-white px-4 dark:border-gray-800 dark:bg-gray-900">
      {/* Mobile sidebar toggle */}
      <button
        onClick={toggleSidebar}
        className="rounded-md p-1.5 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800 lg:hidden"
      >
        <Menu size={20} />
      </button>

      {/* Title */}
      <h1 className="flex-1 truncate text-base font-semibold text-gray-800 dark:text-gray-200">
        {currentConv?.title || '智慧导师'}
      </h1>

      {/* Theme toggle */}
      <button
        onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}
        className="rounded-md p-2 text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800"
      >
        {theme === 'light' ? <Moon size={18} /> : <Sun size={18} />}
      </button>
    </header>
  );
}
