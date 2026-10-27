/**
 * SessionEndDialog
 *
 * "结束本次会话"问卷弹窗:3 道李克特量表题(1=不同意 · 2=一般 · 3=同意)。
 * 提交成功后本次会话由后端标记为已结束(写入 ended_at),父组件负责关闭弹窗
 * 并通过 chatStore.markConversationEnded 同步本地状态。
 */

import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/utils/cn';
import { conversationService } from '@/services/conversation.service';

interface Props {
  open: boolean;
  conversationId: string;
  onClose: () => void;
  onEnded: () => void;
}

const QUESTIONS = [
  '【类人度】整体上，这位AI老师给我的感觉像一位真正的老师。',
  '【共情温度】AI老师能注意到我的情绪变化并鼓励我。',
  '【继续使用意愿】今后我愿意继续使用AI老师辅导我学习。',
];

const OPTIONS = [
  { label: '不同意', value: 1 },
  { label: '一般', value: 2 },
  { label: '同意', value: 3 },
] as const;

export function SessionEndDialog({
  open,
  conversationId,
  onClose,
  onEnded,
}: Props) {
  const [answers, setAnswers] = useState<{
    q1: number | null;
    q2: number | null;
    q3: number | null;
  }>({ q1: null, q2: null, q3: null });
  const [submitting, setSubmitting] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);

  // 每次打开时重置作答
  useEffect(() => {
    if (open) {
      setAnswers({ q1: null, q2: null, q3: null });
    }
  }, [open]);

  // body 滚动锁定 + Escape 关闭 + 初始聚焦
  useEffect(() => {
    if (!open) return;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    panelRef.current?.focus();

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !submitting) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      document.body.style.overflow = prevOverflow;
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [open, submitting, onClose]);

  if (!open) return null;

  const keys = ['q1', 'q2', 'q3'] as const;
  const unanswered = keys.filter((k) => answers[k] === null).length;
  const allAnswered = unanswered === 0;

  const handleSubmit = async () => {
    if (!allAnswered || submitting || !conversationId) return;
    setSubmitting(true);
    try {
      await conversationService.submitQuestionnaire(conversationId, {
        q1_score: answers.q1!,
        q2_score: answers.q2!,
        q3_score: answers.q3!,
      });
      toast.success('问卷已提交，本次会话已结束');
      onEnded();
    } catch {
      toast.error('问卷提交失败，请重试');
    } finally {
      setSubmitting(false);
    }
  };

  return createPortal(
    <div
      className="fixed inset-0 z-[120] flex items-center justify-center bg-black/70 backdrop-blur-sm animate-fade-in"
      onClick={() => {
        if (!submitting) onClose();
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="会话体验问卷"
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
        className="w-[min(560px,92vw)] max-h-[85vh] overflow-y-auto rounded-2xl border border-border-strong bg-bg-elevated p-6 shadow-2xl animate-scale-in focus:outline-none"
      >
        <h2 className="text-16 font-semibold text-text-primary">
          结束本次会话
        </h2>
        <p className="mt-1.5 text-12 text-text-tertiary">
          感谢使用AI老师！请先完成 3
          道体验问卷（每题：1=不同意 · 2=一般 · 3=同意）
        </p>

        <div className="mt-5 flex flex-col gap-5">
          {QUESTIONS.map((q, qi) => (
            <div key={qi}>
              <p className="text-14 text-text-primary">{q}</p>
              <div className="mt-2.5 flex gap-2">
                {OPTIONS.map((opt) => {
                  const selected = answers[keys[qi]] === opt.value;
                  return (
                    <button
                      key={opt.value}
                      type="button"
                      aria-pressed={selected}
                      disabled={submitting}
                      onClick={() =>
                        setAnswers((prev) => ({ ...prev, [keys[qi]]: opt.value }))
                      }
                      className={cn(
                        'flex-1 rounded-xl border px-3 py-2 text-14 transition-colors duration-150',
                        'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent/60',
                        selected
                          ? 'border-accent bg-accent-soft text-accent'
                          : 'border-border-subtle text-text-secondary hover:border-border-strong',
                      )}
                    >
                      {opt.label} {opt.value}
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>

        <div className="mt-6 flex items-center justify-between gap-3">
          <span className="text-12 text-text-tertiary">
            {unanswered > 0 && `还有 ${unanswered} 题未作答`}
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              disabled={submitting}
              className="rounded-xl border border-border-strong px-4 py-2 text-14 text-text-secondary hover:bg-bg-base disabled:cursor-not-allowed disabled:opacity-50"
            >
              暂不结束
            </button>
            <button
              type="button"
              onClick={handleSubmit}
              disabled={!allAnswered || submitting}
              className="flex items-center gap-1.5 rounded-xl bg-accent px-4 py-2 text-14 text-white hover:bg-accent/90 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {submitting && <Loader2 size={14} className="animate-spin" />}
              提交问卷并结束会话
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}
