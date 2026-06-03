import {
  Heart,
  Shield,
  Brain,
  Route,
  Library,
  Users,
  BookOpen,
  Sparkles,
  type LucideIcon,
} from 'lucide-react';
import type { AgentConfig } from '@/data/agentConfigs';

interface Props {
  agent: AgentConfig;
  isActive: boolean;
}

const ICON_MAP: Record<string, LucideIcon> = {
  Heart,
  Shield,
  Brain,
  Route,
  Library,
  Users,
  BookOpen,
  Sparkles,
  HandHeart: Heart,
};

const ICON_TEXT_COLOR_MAP: Record<string, string> = {
  rose: 'text-rose-400',
  amber: 'text-amber-400',
  violet: 'text-violet-400',
  blue: 'text-blue-400',
  emerald: 'text-emerald-400',
  cyan: 'text-cyan-400',
  indigo: 'text-indigo-400',
  pink: 'text-pink-400',
  orange: 'text-orange-400',
};

export function AgentOverview({ agent, isActive }: Props) {
  const Icon = ICON_MAP[agent.icon] ?? Heart;
  const iconText = ICON_TEXT_COLOR_MAP[agent.color] ?? 'text-gray-400';

  return (
    <div className="rounded-2xl border border-white/[0.06] bg-[#0f0f13] overflow-hidden animate-scale-in transition-all duration-200 hover:border-white/[0.1]">
      {/* Blue accent strip */}
      <div className="h-0.5 bg-gradient-to-r from-primary-500 to-primary-600" />

      {/* Content */}
      <div className="p-4">
        <div className="flex items-start gap-3">
          <div className="flex-shrink-0 w-9 h-9 rounded-xl bg-primary-500/10 flex items-center justify-center">
            <Icon className={`w-4.5 h-4.5 ${iconText}`} />
          </div>

          <div className="min-w-0 flex-1">
            <div className="font-semibold text-sm tracking-tight text-gray-200">{agent.displayName}</div>
            <div className="text-xs text-gray-500">{agent.description}</div>
          </div>
        </div>

        <div className="flex items-center gap-2 mt-2.5">
          <span className="text-[11px] bg-primary-500/10 text-primary-400 px-2 py-0.5 rounded-md">
            v{agent.version}
          </span>
          {isActive && (
            <span className="text-xs text-green-400 flex items-center gap-1">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
              运行中
            </span>
          )}
        </div>

        <p className="text-xs text-gray-500 mt-2">
          {agent.promptSummary}
        </p>
      </div>
    </div>
  );
}

export default AgentOverview;
