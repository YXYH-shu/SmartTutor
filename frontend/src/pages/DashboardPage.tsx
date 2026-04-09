import { useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { ChatContainer } from '@/components/chat/ChatContainer';
import { useChatStore } from '@/stores/chatStore';
import { conversationService } from '@/services/conversation.service';
import { chatService } from '@/services/chat.service';

export default function DashboardPage() {
  const { conversationId } = useParams<{ conversationId?: string }>();
  const {
    currentConversationId,
    setCurrentConversation,
    setMessages,
    setConversations,
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

  return (
    <div className="flex h-full flex-col">
      <ChatContainer />
    </div>
  );
}
