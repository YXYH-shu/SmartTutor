import { useState } from 'react';
import { ChevronDown, ChevronRight, Zap, Brain, ArrowRight } from 'lucide-react';
import { useChatStore } from '@/stores/chatStore';
import type { AgentConfig } from '@/data/agentConfigs';

interface Props {
  agent: AgentConfig;
}

export function AgentDesignShowcase({ agent }: Props) {
  const thinkingSteps = useChatStore((s) => s.thinkingSteps);
  const agentTrace = useChatStore((s) => s.agentTrace);
  const [showDesign, setShowDesign] = useState(true);
  const [showPipeline, setShowPipeline] = useState(true);
  const [showLatest, setShowLatest] = useState(true);

  // 直接用 agent.name 匹配后端 SSE step 字段(已是 agent 内部名,如 "cognitive_diagnosis")
  // 不再用 NODE_TO_AGENT 映射,也不再有 fallback 到全部 thinkingSteps 的 bug
  const agentSteps = thinkingSteps.filter(
    (step) => step.step === agent.name || step.label?.includes(agent.displayName),
  );

  // 流式期间的实时数据
  const isRunning = agentSteps.some((s) => s.status === 'running');
  const lastCompletedStream = [...agentSteps]
    .reverse()
    .find((s) => s.status === 'completed' && s.content);

  // 对话结束后的持久化数据(agentTrace 不被清空)
  const traced = agentTrace[agent.name];

  // 综合来源:流式优先,无则取 trace
  const latestContent = lastCompletedStream?.content || traced?.content || '';
  const hasLatest = latestContent.length > 0;

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
                  // 当前所在阶段:已完成步骤数(简化估算,后续可由后端 stage_index 精确化)
                  const completedCount = agentSteps.filter((s) => s.status === 'completed').length;
                  const isStageRunning = isRunning && idx === completedCount;
                  const isStageDone = idx < completedCount;
                  return (
                    <div key={idx} className="flex items-start gap-2">
                      <div className="flex flex-col items-center">
                        <div className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[10px] font-bold ${
                          isStageRunning
                            ? 'bg-primary-500/15 text-primary-400 ring-1 ring-primary-500/30'
                            : isStageDone
                            ? 'bg-primary-500/10 text-primary-400/70'
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

      {/* Latest Analysis Result — 仅展示当前选中 agent 的输出,不再 fallback 到其他 agent */}
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
          {hasLatest && !isRunning && (
            <span className="text-[10px] text-gray-600 ml-1">最新一次</span>
          )}
          {showLatest ? <ChevronDown size={14} className="ml-auto text-gray-500" /> : <ChevronRight size={14} className="ml-auto text-gray-500" />}
        </button>
        {showLatest && (
          <div className="px-3 pb-3">
            {hasLatest ? (
              <div className="rounded-lg bg-white/[0.02] p-2.5">
                <div className="text-xs text-gray-400 leading-relaxed whitespace-pre-wrap">
                  {(() => {
                    try {
                      const parsed = JSON.parse(latestContent);
                      return formatAnalysisResult(agent.name, parsed);
                    } catch {
                      return latestContent;
                    }
                  })()}
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-2 py-4 text-gray-600">
                <Brain size={18} className="opacity-30" />
                <span className="text-xs">尚未观察到 {agent.displayName} 的运行</span>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// 各 agent 输出字段中文映射,未覆盖的 key 直接打原 key
const LABELS_BY_AGENT: Record<string, Record<string, string>> = {
  emotion_analyzer: {
    emotion: '主要情绪',
    intensity: '情感强度',
    trend: '变化趋势',
    learning_intent: '学习意愿',
    suggested_response_tone: '建议语气',
  },
  cognitive_diagnosis: {
    knowledge_states: '知识点状态',
    mastery_rates: '掌握度',
    weak_points: '薄弱点',
    knowledge_graph: '知识图谱',
    diagnosis_source: '诊断来源',
  },
  learning_path: {
    planning_rationale: '规划依据',
    stages: '学习阶段',
    adaptive_rules: '纠偏规则',
    estimated_completion: '预计完成时间',
  },
  resource_recommender: {
    recommendation_text: '推荐说明',
    resources: '推荐资源',
    rationale: '推荐理由',
  },
  study_buddy: {
    recommendation_text: '推荐说明',
    buddies: '推荐学伴',
    group_suggestion: '小组建议',
  },
  knowledge_responder: {
    response_text: '回复内容',
  },
  content_polisher: {
    polished_content: '润色后内容',
    corrections_made: '修正项',
  },
  empathy_generator: {
    empathetic_response: '共情回复',
    psychological_techniques: '心理技巧',
    teacher_persona: '教师人设',
  },
  safety_monitor: {
    risk_level: '风险等级',
    action: '处置动作',
    transformed_query: '转化后查询',
    guidance: '教育引导',
  },
};

function formatAnalysisResult(agentName: string, data: Record<string, unknown>): string {
  const labels = LABELS_BY_AGENT[agentName] || {};
  const lines: string[] = [];

  for (const [key, value] of Object.entries(data)) {
    const label = labels[key] || key;
    // 跳过大对象(如完整知识图谱),只在前端展示关键字段
    if (key === 'knowledge_graph' || key === 'kt_metrics' || key === 'kt_model_info') {
      if (value && typeof value === 'object') {
        const size = Object.keys(value as object).length;
        lines.push(`${label}: <${size} 项,详情见 trace.log>`);
      }
      continue;
    }
    if (Array.isArray(value)) {
      if (value.length === 0) {
        lines.push(`${label}: (空)`);
      } else if (value.length <= 3) {
        lines.push(`${label}: ${JSON.stringify(value, null, 0).slice(0, 200)}`);
      } else {
        lines.push(`${label}: [${value.length} 项] ${JSON.stringify(value.slice(0, 2), null, 0).slice(0, 150)}...`);
      }
    } else if (typeof value === 'object' && value !== null) {
      const size = Object.keys(value as object).length;
      lines.push(`${label}: <${size} 字段对象>`);
    } else {
      lines.push(`${label}: ${value}`);
    }
  }
  return lines.join('\n');
}

export default AgentDesignShowcase;
