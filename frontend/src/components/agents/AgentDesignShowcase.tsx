import { useState } from 'react';
import { ChevronDown, ChevronRight, Zap, Brain, ArrowRight } from 'lucide-react';
import { useChatStore } from '@/stores/chatStore';
import { NODE_TO_AGENT } from '@/data/agentConfigs';
import type { AgentConfig } from '@/data/agentConfigs';

interface Props {
  agent: AgentConfig;
}

export function AgentDesignShowcase({ agent }: Props) {
  const thinkingSteps = useChatStore((s) => s.thinkingSteps);
  const [showDesign, setShowDesign] = useState(true);
  const [showPipeline, setShowPipeline] = useState(true);
  const [showLatest, setShowLatest] = useState(true);

  const agentSteps = thinkingSteps.filter((step) => {
    const mapped = NODE_TO_AGENT[step.step];
    return mapped === agent.name || step.step?.includes(agent.name) || step.label?.includes(agent.name);
  });
  const allSteps = agentSteps.length > 0 ? agentSteps : thinkingSteps.length > 0 ? thinkingSteps : [];

  const isRunning = allSteps.some((s) => s.status === 'running');
  const lastCompleted = [...allSteps].reverse().find((s) => s.status === 'completed' && s.content);

  return (
    <div className="space-y-3 animate-scale-in anim-delay-200">
      {/* Design Notes */}
      {agent.designNotes && (
        <div className="rounded-2xl border border-white/[0.06] bg-[#0f0f13] overflow-hidden">
          <button
            className="flex w-full items-center gap-2 px-3 py-2.5 text-xs font-medium text-gray-400 hover:bg-white/[0.02] transition-all duration-200"
            onClick={() => setShowDesign((p) => !p)}
          >
            <Zap size={14} className="text-primary-400" />
            <span>设计原理</span>
            {showDesign ? <ChevronDown size={14} className="ml-auto text-gray-500" /> : <ChevronRight size={14} className="ml-auto text-gray-500" />}
          </button>
          {showDesign && (
            <div className="px-3 pb-3">
              <p className="text-xs leading-relaxed text-gray-500">
                {agent.designNotes}
              </p>
            </div>
          )}
        </div>
      )}

      {/* Thinking Process Pipeline */}
      {agent.thinkingProcess && (
        <div className="rounded-2xl border border-white/[0.06] bg-[#0f0f13] overflow-hidden">
          <button
            className="flex w-full items-center gap-2 px-3 py-2.5 text-xs font-medium text-gray-400 hover:bg-white/[0.02] transition-all duration-200"
            onClick={() => setShowPipeline((p) => !p)}
          >
            <Brain size={14} className="text-primary-400" />
            <span>思考链路</span>
            <span className="ml-1 rounded-md bg-primary-500/10 px-1.5 py-0.5 text-[10px] text-primary-400">
              {agent.thinkingProcess.stages.length} 阶段
            </span>
            {showPipeline ? <ChevronDown size={14} className="ml-auto text-gray-500" /> : <ChevronRight size={14} className="ml-auto text-gray-500" />}
          </button>
          {showPipeline && (
            <div className="px-3 pb-3">
              <div className="space-y-0">
                {agent.thinkingProcess.stages.map((stage, idx) => {
                  const isStageRunning = isRunning && idx === allSteps.filter(s => s.status === 'completed').length;
                  return (
                    <div key={idx} className="flex items-start gap-2">
                      <div className="flex flex-col items-center">
                        <div className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[10px] font-bold ${
                          isStageRunning
                            ? 'bg-primary-500/15 text-primary-400 ring-1 ring-primary-500/30'
                            : 'bg-white/[0.04] text-gray-500'
                        }`}>
                          {idx + 1}
                        </div>
                        {idx < agent.thinkingProcess!.stages.length - 1 && (
                          <div className="w-px h-4 bg-white/[0.06]" />
                        )}
                      </div>
                      <div className="pb-3">
                        <div className="flex items-center gap-1.5">
                          <span className="text-xs font-medium text-gray-300">{stage.name}</span>
                          {isStageRunning && (
                            <span className="h-1.5 w-1.5 rounded-full bg-primary-400 animate-pulse" />
                          )}
                        </div>
                        <p className="text-[11px] text-gray-500">{stage.description}</p>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Latest Analysis Result */}
      <div className="rounded-2xl border border-white/[0.06] bg-[#0f0f13] overflow-hidden">
        <button
          className="flex w-full items-center gap-2 px-3 py-2.5 text-xs font-medium text-gray-400 hover:bg-white/[0.02] transition-all duration-200"
          onClick={() => setShowLatest((p) => !p)}
        >
          <ArrowRight size={14} className="text-primary-400" />
          <span>最近分析结果</span>
          {isRunning && (
            <span className="flex items-center gap-1">
              <span className="h-1.5 w-1.5 rounded-full bg-primary-400 animate-pulse" />
              <span className="text-[10px] text-primary-400">运行中</span>
            </span>
          )}
          {showLatest ? <ChevronDown size={14} className="ml-auto text-gray-500" /> : <ChevronRight size={14} className="ml-auto text-gray-500" />}
        </button>
        {showLatest && (
          <div className="px-3 pb-3">
            {lastCompleted ? (
              <div className="rounded-lg bg-white/[0.02] p-2.5">
                <div className="text-xs text-gray-400 leading-relaxed whitespace-pre-wrap">
                  {(() => {
                    try {
                      const parsed = JSON.parse(lastCompleted.content);
                      return formatAnalysisResult(parsed);
                    } catch {
                      return lastCompleted.content;
                    }
                  })()}
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-2 py-4 text-gray-600">
                <Brain size={18} className="opacity-30" />
                <span className="text-xs">发送消息后将展示分析结果</span>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function formatAnalysisResult(data: Record<string, unknown>): string {
  const lines: string[] = [];
  const LABELS: Record<string, string> = {
    emotion: '主要情绪',
    intensity: '情感强度',
    trend: '变化趋势',
    learning_intent: '学习意愿',
    suggested_response_tone: '建议语气',
  };
  for (const [key, value] of Object.entries(data)) {
    const label = LABELS[key] || key;
    if (typeof value === 'object' && value !== null) {
      lines.push(`${label}: ${JSON.stringify(value, null, 0)}`);
    } else {
      lines.push(`${label}: ${value}`);
    }
  }
  return lines.join('\n');
}

export default AgentDesignShowcase;
