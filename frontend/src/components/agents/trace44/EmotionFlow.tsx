/**
 * 情感分析可视化：感知输入 → 三分类判定 → 情感模型 → 下游分发（按右栏自适应设计）。
 *
 * - 模型段展示自研微调情感模型（AGENT_CONFIGS 会被运行时后端配置覆盖为真实值）。
 * - GUIDE 兑现轮情感分析实跑，本组件展示的就是当轮判定。
 */
import { Cpu, Frown, HeartPulse, Meh, MessageSquare, Share2, Smile, type LucideIcon } from 'lucide-react';
import { AGENT_CONFIGS } from '@/data/agentConfigs';
import { Chip, EmptyState, FieldGrid, FlowShell, Panel, ResultBanner, Stage, type Tone } from '../trace43/primitives';
import { buildEmotionView } from './emotionAdapter';
import type { EmotionPolarity, Json } from './types';

const POLARITY_TONE: Record<EmotionPolarity, Tone> = {
  positive: 'success',
  negative: 'warning',
  neutral: 'info',
  '': 'neutral',
};
const POLARITY_ICON: Record<EmotionPolarity, LucideIcon> = {
  positive: Smile,
  negative: Frown,
  neutral: Meh,
  '': HeartPulse,
};

interface EmotionFlowProps {
  output: Json | null;
  /** 本轮被分析的学生消息 */
  message?: string;
  isRunning: boolean;
  onBack: () => void;
  onClose: () => void;
}

export function EmotionFlow({ output, message, isRunning, onBack, onClose }: EmotionFlowProps) {
  const view = buildEmotionView(output);
  if (!view.hasData) {
    return (
      <FlowShell icon={HeartPulse} title="情感分析" subtitle="emotion_analyzer · 情感智能体" onBack={onBack} onClose={onClose}>
        <EmptyState running={isRunning} text="本轮暂无情感分析输出" />
      </FlowShell>
    );
  }
  const tone = POLARITY_TONE[view.polarity];
  const Icon = POLARITY_ICON[view.polarity];
  const llm = AGENT_CONFIGS.emotion_analyzer?.llmConfig;
  return (
    <FlowShell icon={HeartPulse} title="情感分析" subtitle="emotion_analyzer · 情感智能体" onBack={onBack} onClose={onClose}>
      <ResultBanner
        icon={Icon}
        tone={tone}
        label="EMOTION"
        title={view.polarityLabel || '已判定'}
        text={view.reason || '本轮情感判定完成，结果已写入会话情感历史。'}
      />

      <Stage index={1} title="感知输入" subtitle="只读取本轮学生消息" icon={MessageSquare}>
        <Panel className="text-13 leading-relaxed text-text-secondary">
          {message ? message : '（本轮消息不可用）'}
        </Panel>
      </Stage>

      <Stage index={2} title="三分类判定" subtitle="positive / negative / neutral" icon={HeartPulse} tone={tone}>
        <div className="flex flex-col gap-2.5">
          <Panel className="flex items-center gap-2.5">
            <Chip tone={tone} icon={Icon}>{view.polarity || '未知'}</Chip>
            <span className="text-14 font-display font-semibold text-text-primary">{view.polarityLabel || '—'}</span>
          </Panel>
          {view.reason && (
            <div className="rounded-md border-l-2 border-accent/60 bg-bg-base px-3.5 py-3 text-13 leading-relaxed text-text-primary">
              {view.reason}
            </div>
          )}
        </div>
      </Stage>

      <Stage index={3} title="情感模型" subtitle="自研微调 · 三分类专精" icon={Cpu} tone="accent">
        <Panel className="flex flex-col gap-2.5">
          <div className="flex items-center gap-2">
            <Chip tone="accent">自研微调</Chip>
            <span className="text-12 text-text-secondary">基于 Qwen3.5-9B 的情感三分类专精模型</span>
          </div>
          {llm && (
            <FieldGrid
              items={[
                { label: 'MODEL', value: llm.model },
                { label: 'ENDPOINT', value: llm.baseUrl ?? null },
                { label: 'TEMPERATURE', value: String(llm.temperature) },
                { label: 'MAX TOKENS', value: String(llm.maxTokens) },
              ]}
            />
          )}
        </Panel>
      </Stage>

      <Stage index={4} title="下游分发" subtitle="判定结果写入 emotion_history" icon={Share2} isLast state="muted" mutedHint="结果供智能决策路由与共情回应生成使用；强负面时情感分析会成为本轮重点 agent。" />
    </FlowShell>
  );
}
