/** emotion_analyzer 输出 → EmotionView（脏数据兜底） */
import type { EmotionPolarity, EmotionView, Json } from './types';

const POLARITY_LABELS: Record<EmotionPolarity, string> = {
  positive: '积极',
  negative: '消极',
  neutral: '平静',
  '': '',
};

function normalizePolarity(value: unknown): EmotionPolarity {
  return value === 'positive' || value === 'negative' || value === 'neutral' ? value : '';
}

export function buildEmotionView(raw: Json | null): EmotionView {
  const polarity = normalizePolarity(raw?.emotion);
  const reason = typeof raw?.reason === 'string' ? raw.reason.trim() : '';
  return {
    polarity,
    polarityLabel: POLARITY_LABELS[polarity],
    reason,
    hasData: polarity !== '' || reason !== '',
  };
}
