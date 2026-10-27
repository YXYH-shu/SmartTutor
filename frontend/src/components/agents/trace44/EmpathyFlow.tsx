/**
 * 共情回应可视化：情感输入 → 共情策略 → 注入对比 → 回应全文（右栏自适应设计）。
 *
 * 注入对比段做句子级 diff：以同轮润色/知识回应文本为"前"、共情回应为"后"，
 * 高亮 after 中新注入的共情内容；两侧数据缺失时回退为纯渲染。
 */
import { memo } from 'react';
import ReactMarkdown from 'react-markdown';
import { FileDiff, HeartHandshake, HeartPulse, MessageSquareText, Sparkles } from 'lucide-react';
import { Chip, EmptyState, FlowShell, Panel, ResultBanner, Stage, type Tone } from '../trace43/primitives';
import { buildEmotionView } from './emotionAdapter';
import { buildEmpathyView } from './empathyAdapter';
import { diffSegments } from './diff';
import type { EmotionPolarity, Json } from './types';

const POLARITY_TONE: Record<EmotionPolarity, Tone> = {
  positive: 'success',
  negative: 'warning',
  neutral: 'info',
  '': 'neutral',
};

interface EmpathyFlowProps {
  output: Json | null;
  /** 同轮 emotion_analyzer 输出，用于展示共情的情感输入 */
  emotionOutput?: Json | null;
  /** 同轮润色/知识回应文本（diff 的"前"侧） */
  baseContent?: string | null;
  isRunning: boolean;
  onBack: () => void;
  onClose: () => void;
}

function extractText(output: Json | null, keys: string[]): string {
  if (!output) return '';
  for (const key of keys) {
    const value = output[key];
    if (typeof value === 'string' && value.trim()) return value.trim();
  }
  return '';
}

const DiffView = memo(function DiffView({ before, after }: { before: string; after: string }) {
  const segments = diffSegments(before, after);
  const addedCount = segments.filter((s) => s.kind === 'added').length;
  return (
    <div className="flex flex-col gap-2">
      <Panel>
        <p className="mb-1.5 font-mono text-11 uppercase tracking-wide text-text-tertiary">知识回应 · 前</p>
        <p className="text-12 leading-relaxed text-text-tertiary line-clamp-4">{before}</p>
      </Panel>
      <Panel>
        <div className="mb-1.5 flex items-center justify-between">
          <p className="font-mono text-11 uppercase tracking-wide text-text-tertiary">共情回应 · 后</p>
          {addedCount > 0 && <Chip tone="success">注入 {addedCount} 段</Chip>}
        </div>
        <p className="text-13 leading-relaxed">
          {segments.map((seg, i) =>
            seg.kind === 'added' ? (
              <mark
                key={i}
                className="rounded-sm bg-status-success/15 px-1 text-text-primary [box-shadow:inset_2px_0_0_rgb(var(--color-status-success))]"
                title="共情注入"
              >
                {seg.text}
              </mark>
            ) : seg.kind === 'removed' ? (
              <span key={i} className="text-text-tertiary/60 line-through">
                {seg.text}
              </span>
            ) : (
              <span key={i} className="text-text-secondary">
                {seg.text}
              </span>
            ),
          )}
        </p>
      </Panel>
    </div>
  );
});

export function EmpathyFlow({ output, emotionOutput, baseContent, isRunning, onBack, onClose }: EmpathyFlowProps) {
  const view = buildEmpathyView(output);
  if (!view.hasData) {
    return (
      <FlowShell icon={HeartHandshake} title="共情回应" subtitle="empathy_generator · 情感智能体" onBack={onBack} onClose={onClose}>
        <EmptyState running={isRunning} text="本轮暂无共情回应输出（仅在情感需要支持时生成）" />
      </FlowShell>
    );
  }
  const emotion = buildEmotionView(emotionOutput ?? null);
  const emotionTone = POLARITY_TONE[emotion.polarity];
  const beforeText = (baseContent ?? '').trim();
  const hasDiff = beforeText !== '' && beforeText !== view.response;
  return (
    <FlowShell icon={HeartHandshake} title="共情回应" subtitle="empathy_generator · 情感智能体" onBack={onBack} onClose={onClose}>
      <ResultBanner
        icon={HeartHandshake}
        tone="accent"
        label="EMPATHY"
        title={view.persona || '共情回应已生成'}
        text={view.techniques.length > 0 ? `在知识回应之上叠加：${view.techniques.join(' · ')}` : '在知识回应之上叠加情感支持。'}
      />

      <Stage
        index={1}
        title="情感输入"
        subtitle="来自同轮情感分析"
        icon={HeartPulse}
        tone={emotionTone}
        state={emotion.hasData ? 'active' : 'muted'}
        mutedHint="本轮无情感分析数据"
      >
        <Panel className="flex flex-col gap-2">
          <div className="flex items-center gap-2">
            <Chip tone={emotionTone}>{emotion.polarity || '未知'}</Chip>
            <span className="text-12 font-medium text-text-primary">{emotion.polarityLabel || '—'}</span>
          </div>
          {emotion.reason && (
            <p className="text-12 leading-relaxed text-text-secondary">{emotion.reason}</p>
          )}
        </Panel>
      </Stage>

      <Stage index={2} title="共情策略" subtitle="回应中采用的心理支持技巧" icon={Sparkles}>
        {view.techniques.length > 0 ? (
          <ol className="space-y-1.5">
            {view.techniques.map((technique, i) => (
              <li key={technique}>
                <Panel className="flex items-start gap-2.5">
                  <span className="mt-px font-mono text-11 text-accent">{String(i + 1).padStart(2, '0')}</span>
                  <span className="text-12 font-medium leading-relaxed text-text-primary">{technique}</span>
                </Panel>
              </li>
            ))}
          </ol>
        ) : (
          <Panel className="text-12 text-text-tertiary">未显式标注技巧</Panel>
        )}
      </Stage>

      {hasDiff && (
        <Stage index={3} title="注入对比" subtitle="高亮部分为注入的共情内容" icon={FileDiff}>
          <DiffView before={beforeText} after={view.response} />
        </Stage>
      )}

      <Stage index={hasDiff ? 4 : 3} title="回应全文" subtitle="最终叠加到知识回应之后" icon={MessageSquareText} isLast>
        <Panel className="[&_*]:my-0">
          <div className="prose prose-sm prose-invert max-w-none text-text-primary">
            <ReactMarkdown>{view.response}</ReactMarkdown>
          </div>
        </Panel>
      </Stage>
    </FlowShell>
  );
}
