import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Plus,
  MessageSquare,
  Pencil,
  Trash2,
  LogOut,
  User,
  BookOpen,
  Lightbulb,
  ChevronLeft,
} from 'lucide-react';
import { cn } from '@/utils/cn';
import { useChatStore } from '@/stores/chatStore';
import { useAuthStore } from '@/stores/authStore';
import { useUIStore } from '@/stores/uiStore';
import { conversationService } from '@/services/conversation.service';
import { toast } from 'sonner';

export function Sidebar() {
  const navigate = useNavigate();
  const { user, logout } = useAuthStore();
  const {
    conversations,
    currentConversationId,
    addConversation,
    removeConversation,
    updateConversationTitle,
    setCurrentConversation,
  } = useChatStore();
  const { sidebarOpen, toggleSidebar } = useUIStore();

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');

  const grouped = groupByDate(conversations);

  const handleNew = async () => {
    try {
      const conv = await conversationService.create({ title: '新对话' });
      addConversation(conv);
      setCurrentConversation(conv.id);
      navigate(`/dashboard/chat/${conv.id}`);
    } catch {
      toast.error('创建对话失败');
    }
  };

  const handleSelect = (id: string) => {
    setCurrentConversation(id);
    navigate(`/dashboard/chat/${id}`);
  };

  const handleDelete = async (id: string) => {
    if (!confirm('确定删除此对话？')) return;
    try {
      await conversationService.delete(id);
      removeConversation(id);
      if (currentConversationId === id) navigate('/dashboard/chat');
    } catch {
      toast.error('删除失败');
    }
  };

  const startRename = (id: string, currentTitle: string) => {
    setEditingId(id);
    setEditTitle(currentTitle || '新对话');
  };

  const finishRename = async () => {
    if (!editingId || !editTitle.trim()) {
      setEditingId(null);
      return;
    }
    try {
      await conversationService.updateTitle(editingId, editTitle.trim());
      updateConversationTitle(editingId, editTitle.trim());
    } catch {
      toast.error('重命名失败');
    }
    setEditingId(null);
  };

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  if (!sidebarOpen) return null;

  return (
    <aside className="flex h-screen w-64 flex-col border-r border-white/[0.06] bg-[#0a0a0f] animate-fade-in">
      {/* Logo */}
      <div className="flex items-center gap-2.5 px-4 py-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary-600 text-white shadow-sm">
          <BookOpen size={16} />
        </div>
        <span className="text-sm font-semibold tracking-tight text-white">
          智慧导师
        </span>
        <button
          onClick={toggleSidebar}
          className="ml-auto rounded-md p-1 text-gray-500 hover:text-gray-300 transition-colors"
        >
          <ChevronLeft size={16} />
        </button>
      </div>

      {/* New Chat Button */}
      <div className="px-3 pb-2">
        <button
          onClick={handleNew}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-primary-600 hover:bg-primary-500 px-4 py-2 text-sm font-medium text-white shadow-sm transition-all duration-200 active:scale-[0.98]"
        >
          <Plus size={16} />
          新建对话
        </button>
      </div>

      {/* Conversation List */}
      <div className="flex-1 overflow-y-auto px-2 scrollbar-thin">
        {Object.entries(grouped).map(([label, convs]) => (
          <div key={label} className="mb-2">
            <p className="px-2 py-1.5 text-[11px] font-medium text-gray-500 tracking-wide">
              {label}
            </p>
            {convs.map((conv) => (
              <div
                key={conv.id}
                className={cn(
                  'group flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition-all duration-200 cursor-pointer',
                  conv.id === currentConversationId
                    ? 'bg-primary-500/10 text-primary-300'
                    : 'text-gray-400 hover:bg-white/[0.04] hover:text-gray-200',
                )}
                onClick={() => handleSelect(conv.id)}
              >
                <MessageSquare size={14} className="shrink-0 opacity-40" />
                {editingId === conv.id ? (
                  <input
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                    onBlur={finishRename}
                    onKeyDown={(e) => e.key === 'Enter' && finishRename()}
                    onClick={(e) => e.stopPropagation()}
                    className="flex-1 rounded border border-white/10 bg-white/5 text-gray-200 px-1.5 text-sm outline-none focus:border-primary-500"
                    autoFocus
                  />
                ) : (
                  <span className="flex-1 truncate">{conv.title || '新对话'}</span>
                )}
                <div className="hidden gap-1 group-hover:flex">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      startRename(conv.id, conv.title || '');
                    }}
                    className="rounded p-0.5 text-gray-500 hover:text-gray-300"
                  >
                    <Pencil size={12} />
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDelete(conv.id);
                    }}
                    className="rounded p-0.5 text-gray-500 hover:text-red-400"
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        ))}
      </div>

      {/* User Section */}
      <div className="border-t border-white/[0.06] px-3 py-3">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary-600 text-xs font-bold text-white">
            {user?.username?.charAt(0).toUpperCase() || 'U'}
          </div>
          <span className="flex-1 truncate text-sm text-gray-300">
            {user?.username || '用户'}
          </span>
          <button
            onClick={handleLogout}
            title="退出登录"
            className="rounded-lg p-1.5 text-gray-500 hover:text-red-400 transition-colors"
          >
            <LogOut size={15} />
          </button>
        </div>
      </div>
    </aside>
  );
}

function groupByDate(convs: { id: string; title: string | null; updated_at: string }[]) {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today.getTime() - 86_400_000);

  const groups: Record<string, typeof convs> = { 今天: [], 昨天: [], 更早: [] };

  for (const c of convs) {
    const d = new Date(c.updated_at);
    if (d >= today) groups['今天'].push(c);
    else if (d >= yesterday) groups['昨天'].push(c);
    else groups['更早'].push(c);
  }

  return Object.fromEntries(Object.entries(groups).filter(([, v]) => v.length > 0));
}
