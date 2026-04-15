import { useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ChatContainer } from '@/components/chat/ChatContainer';
import { useChatStore } from '@/stores/chatStore';
import { conversationService } from '@/services/conversation.service';
import { chatService } from '@/services/chat.service';
import { toast } from 'sonner';

const actionLabels: Record<string, string> = {
  diagnosis: '开始诊断',
  plan: '制定计划',
  companion: '找学习伙伴',
  review: '复习评估',
};

export default function DashboardPage() {
  const { conversationId } = useParams<{ conversationId?: string }>();
  const navigate = useNavigate();
  const {
    currentConversationId,
    setCurrentConversation,
    setMessages,
    setConversations,
    addConversation,
  } = useChatStore();

  /* ── Load conversation list on mount ─────────────────────── */
  useEffect(() => {
    (async () => {
      try {
        const res = await conversationService.list(1, 50);
        setConversations(res.items);
      } catch {
        // silently fail – sidebar will show empty
      }
    })();
  }, [setConversations]);

  /* ── Load messages when conversationId changes ───────────── */
  useEffect(() => {
    if (!conversationId) {
      setCurrentConversation(null);
      return;
    }

    (async () => {
      try {
        setCurrentConversation(conversationId);
        const msgs = await chatService.getHistory(conversationId, undefined, 100);
        setMessages(msgs);
      } catch {
        setMessages([]);
      }
    })();
  }, [conversationId, setCurrentConversation, setMessages]);

  /* ── Quick action: create conversation and navigate ──────── */
  const handleQuickAction = async (action: string) => {
    try {
      const conv = await conversationService.create({
        title: actionLabels[action] || '新对话',
      });
      addConversation(conv);
      setCurrentConversation(conv.id);
      navigate(`/dashboard/chat/${conv.id}`);
    } catch {
      toast.error('创建对话失败');
    }
  };

  return (
    <div className="flex h-full flex-col">
      <ChatContainer onQuickAction={handleQuickAction} />
    </div>
  );
}
