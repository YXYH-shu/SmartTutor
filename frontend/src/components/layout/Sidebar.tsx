import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  Plus,
  Pencil,
  Trash2,
  LogOut,
  BookOpen,
  BarChart3,
  ChevronLeft,
} from 'lucide-react';
import { cn } from '@/utils/cn';
import { useChatStore } from '@/stores/chatStore';
import { useAuthStore } from '@/stores/authStore';
import { useUIStore } from '@/stores/uiStore';
import { conversationService } from '@/services/conversation.service';
import { SessionThumbnail } from '@/components/sidebar/SessionThumbnail';
import { toast } from 'sonner';

export function Sidebar() {
  const navigate = useNavigate();
  const location = useLocation();
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
  const ktDiagnosisActive = location.pathname.startsWith('/dashboard/kt-diagnosis');

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

  const handleKtDiagnosis = () => {
    navigate('/dashboard/kt-diagnosis');
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
    <aside className="flex h-screen w-64 flex-col border-r border-border-subtle bg-bg-base animate-fade-in">
      {/* Logo */}
      <div className="flex items-center gap-2.5 px-4 py-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent text-white shadow-sm">
          <BookOpen size={16} />
        </div>
        <span className="font-display text-14 font-semibold tracking-tight text-text-primary">
          智慧导师
        </span>
        <button
          onClick={toggleSidebar}
          className="ml-auto rounded-md p-1 text-text-tertiary hover:text-text-secondary transition-colors"
        >
          <ChevronLeft size={16} />
        </button>
      </div>

      {/* New Chat Button */}
      <div className="px-3 pb-2">
        <button
          onClick={handleNew}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-accent hover:bg-accent/90 px-4 py-2 text-14 font-medium text-white shadow-sm transition-all duration-200 active:scale-[0.98]"
        >
          <Plus size={16} />
          新建对话
        </button>
      </div>

      {/* Modules — 仅在 KT standalone 模式下显示 iframe 入口 */}
      {import.meta.env.VITE_KT_STANDALONE === 'true' && (
        <div className="px-2 pb-2">
          <p className="px-2 py-1.5 text-11 font-medium text-text-tertiary tracking-wide">
            功能模块
          </p>
          <button
            onClick={handleKtDiagnosis}
            className={cn(
              'flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-14 transition-all duration-200',
              ktDiagnosisActive
                ? 'bg-accent-soft text-accent'
                : 'text-text-secondary hover:bg-bg-elevated/50 hover:text-text-primary',
            )}
          >
            <BarChart3 size={14} className="shrink-0 opacity-60 text-text-secondary" />
            <span className="flex-1 truncate">学情分析</span>
          </button>
        </div>
      )}

      {/* Conversation List */}
      <div className="flex-1 overflow-y-auto px-2 scrollbar-thin">
        {Object.entries(grouped).map(([label, convs]) => (
          <div key={label} className="mb-2">
            <p className="px-2 py-1.5 text-11 font-medium text-text-tertiary tracking-wide">
              {label}
            </p>
            {convs.map((conv) => (
              <div
                key={conv.id}
                className={cn(
                  'group flex max-h-14 items-center gap-2 rounded-lg px-3 py-1.5 text-14 transition-all duration-200 cursor-pointer',
                  conv.id === currentConversationId
                    ? 'bg-accent-soft text-accent'
                    : 'text-text-secondary hover:bg-bg-elevated/50 hover:text-text-primary',
                )}
                onClick={() => handleSelect(conv.id)}
              >
                {editingId === conv.id ? (
                  <input
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                    onBlur={finishRename}
                    onKeyDown={(e) => e.key === 'Enter' && finishRename()}
                    onClick={(e) => e.stopPropagation()}
                    className="flex-1 rounded-sm border border-border-subtle bg-bg-elevated/50 text-text-primary px-1.5 text-14 outline-none focus:border-accent"
                    autoFocus
                  />
                ) : (
                  <div className="min-w-0 flex-1">
                    <SessionThumbnail
                      conversation={conv}
                      isActive={conv.id === currentConversationId}
                    />
                  </div>
                )}
                <div className="hidden shrink-0 gap-1 group-hover:flex">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      startRename(conv.id, conv.title || '');
                    }}
                    className="rounded-sm p-0.5 text-text-tertiary hover:text-text-secondary"
                  >
                    <Pencil size={12} />
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDelete(conv.id);
                    }}
                    className="rounded-sm p-0.5 text-text-tertiary hover:text-status-error"
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
      <div className="border-t border-border-subtle px-3 py-3">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-accent text-12 font-bold text-white">
            {user?.username?.charAt(0).toUpperCase() || 'U'}
          </div>
          <span className="flex-1 truncate text-14 text-text-secondary">
            {user?.username || '用户'}
          </span>
          <button
            onClick={handleLogout}
            title="退出登录"
            className="rounded-lg p-1.5 text-text-tertiary hover:text-status-error transition-colors"
          >
            <LogOut size={15} />
          </button>
        </div>
      </div>
    </aside>
  );
}

function groupByDate<T extends { id: string; updated_at: string }>(convs: T[]): Record<string, T[]> {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today.getTime() - 86_400_000);

  const groups: Record<string, T[]> = { 今天: [], 昨天: [], 更早: [] };

  for (const c of convs) {
    const d = new Date(c.updated_at);
    if (d >= today) groups['今天'].push(c);
    else if (d >= yesterday) groups['昨天'].push(c);
    else groups['更早'].push(c);
  }

  return Object.fromEntries(Object.entries(groups).filter(([, v]) => v.length > 0)) as Record<string, T[]>;
}
