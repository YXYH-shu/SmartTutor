import { Cpu } from 'lucide-react';
import type { AgentLLMConfig } from '@/data/agentConfigs';

interface Props {
  config: AgentLLMConfig;
}

export function AgentLLMConfig({ config }: Props) {
  return (
    <div className="rounded-2xl border border-white/[0.06] bg-[#0f0f13] p-3 animate-scale-in anim-delay-100 transition-all duration-200 hover:border-white/[0.1]">
      <div className="space-y-3">
        <div className="text-sm font-medium text-gray-300">
          模型配置
        </div>

        <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-md bg-primary-500/10 text-primary-400 border border-primary-500/15">
          <Cpu size={12} />
          {config.model}
        </span>

        <div>
          <div className="flex justify-between text-xs text-gray-500">
            <span>温度</span>
            <span>{config.temperature}</span>
          </div>
          <div className="mt-1 h-1 w-full rounded-full bg-white/[0.04]">
            <div
              className="h-full rounded-full bg-gradient-to-r from-primary-500 to-primary-400"
              style={{ width: `${config.temperature * 100}%` }}
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2 text-xs">
          <div>
            <div className="text-gray-500">最大Token</div>
            <div className="font-medium text-gray-300">{config.maxTokens.toLocaleString()}</div>
          </div>
          <div>
            <div className="text-gray-500">超时</div>
            <div className="font-medium text-gray-300">{config.timeout}s</div>
          </div>
          <div>
            <div className="text-gray-500">重试</div>
            <div className="font-medium text-gray-300">{config.maxRetries}次</div>
          </div>
          <div>
            <div className="text-gray-500">思考模式</div>
            <div className="font-medium flex items-center gap-1 text-gray-300">
              <span
                className={`inline-block h-1.5 w-1.5 rounded-full ${
                  config.thinking ? 'bg-green-400' : 'bg-gray-600'
                }`}
              />
              {config.thinking ? '开启' : '关闭'}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default AgentLLMConfig;
