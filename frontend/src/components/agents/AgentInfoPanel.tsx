import { X, Cpu } from 'lucide-react';
import { useUIStore } from '@/stores/uiStore';
import { useChatStore } from '@/stores/chatStore';
import { AGENT_CONFIGS, AGENT_DISPLAY_ORDER } from '@/data/agentConfigs';
import { AgentOverview } from './AgentOverview';
import { AgentLLMConfig } from './AgentLLMConfig';
import { AgentDesignShowcase } from './AgentDesignShowcase';

export function AgentInfoPanel() {
  const selectedAgent = useUIStore((s) => s.selectedAgent);
  const setRightPanelOpen = useUIStore((s) => s.setRightPanelOpen);
  const setSelectedAgent = useUIStore((s) => s.setSelectedAgent);
  // 直接用后端 SSE 推的 step 字段(agent 内部名)匹配,不再需要 NODE_TO_AGENT 映射
  const thinkingSteps = useChatStore((s) => s.thinkingSteps);

  const agent = AGENT_CONFIGS[selectedAgent];
  if (!agent) return null;

  // isActive 判断:后端推的 step.step 已经是 agent 内部名(如 "cognitive_diagnosis"),
  // 直接对比 selectedAgent。空 step 字段(仅有 label)时退化为 label.includes
  const isActive = thinkingSteps.some(
    (step) =>
      step.status === 'running' &&
      (step.step === selectedAgent ||
        (!step.step && step.label?.includes(agent.displayName))),
  );

  const close = () => setRightPanelOpen(false);

  return (
    <div className="flex h-full w-80 flex-col border-l border-white/[0.06] bg-[#0a0a0f] animate-slide-in-right">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3">
        <div className="flex items-center gap-2">
          <Cpu size={16} className="text-primary-400" />
          <h2 className="text-sm font-semibold text-gray-200">智能体</h2>
        </div>
        <button
          onClick={close}
          className="rounded-lg p-1 text-gray-500 hover:bg-white/[0.04] hover:text-gray-300 transition-all duration-200"
        >
          <X size={16} />
        </button>
      </div>

      {/* Agent Selector */}
      <div className="border-b border-white/[0.06] px-4 py-2">
        <select
          value={selectedAgent}
          onChange={(e) => setSelectedAgent(e.target.value)}
          className="w-full rounded-xl border border-white/[0.08] bg-white/[0.03] px-3 py-1.5 text-sm text-gray-300 focus:border-primary-500/40 focus:outline-none focus:ring-1 focus:ring-primary-500/20 transition-all duration-200"
        >
          {AGENT_DISPLAY_ORDER.map((key) => {
            const config = AGENT_CONFIGS[key];
            if (!config) return null;
            return (
              <option key={key} value={key}>
                {config.displayName}
              </option>
            );
          })}
        </select>
      </div>

      {/* Scrollable content */}
      <div className="flex-1 space-y-3 overflow-y-auto p-4 scrollbar-thin">
        <AgentOverview agent={agent} isActive={isActive} />
        <AgentLLMConfig config={agent.llmConfig} />
        <AgentDesignShowcase agent={agent} />
      </div>
    </div>
  );
}

export default AgentInfoPanel;
