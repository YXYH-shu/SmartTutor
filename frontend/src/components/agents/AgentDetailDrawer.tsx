/**
 * AgentDetailDrawer
 *
 * 点击 Hero / Ensemble / Trace Timeline 任何 agent 卡片时,在右栏内浮层覆盖显示。
 * 数据来源:
 *   - AGENT_CONFIGS[name]: 静态元数据(displayName/version/llmConfig/promptSummary/thinkingProcess)
 *   - chatStore.agentTrace[name].content: 本轮实际输出 JSON 字符串
 *   - AGENT_HIGHLIGHT_FIELDS[name]: 本轮输出要重点展示的字段
 *
 * 渲染:绝对定位覆盖 AgentInfoPanel 的 relative 容器,4 段竖排可滚动。
 */

import { X } from 'lucide-react';
import { useChatStore } from '@/stores/chatStore';
import { AGENT_CONFIGS, AGENT_HIGHLIGHT_FIELDS } from '@/data/agentConfigs';
import { getIcon, getValueByPath, parseAgentContent } from './agentUtils';
import { ResourceRecommendationFlow } from './ResourceRecommendationFlow';
import { StudyBuddyFlow } from './StudyBuddyFlow';
import type { ResourceRecommendationOutput, StudyBuddyOutput } from '@/types';

export function AgentDetailDrawer() {
  const selectedDetailAgent = useChatStore((s) => s.selectedDetailAgent);
  const setSelectedDetailAgent = useChatStore((s) => s.setSelectedDetailAgent);
  const agentTrace = useChatStore((s) => s.agentTrace);
  const messages = useChatStore((s) => s.messages);
  const currentAgent = useChatStore((s) => s.currentAgent);
  const currentTurn = useChatStore((s) => s.currentTurn);

  if (!selectedDetailAgent) return null;
  if (selectedDetailAgent === 'resource_recommender') {
    const liveOutput = parseAgentContent(agentTrace.resource_recommender?.content);
    const currentMessage = [...messages]
      .reverse()
      .find((message) => message.role === 'user')?.content;
    const isRunning =
      !liveOutput &&
      (currentAgent === 'resource_recommender' ||
        currentTurn?.agentTimeline.some(
          (item) => item.agentName === 'resource_recommender' && item.status === 'running',
        ) === true);

    return (
      <ResourceRecommendationFlow
        onBack={() => setSelectedDetailAgent(null)}
        onClose={() => setSelectedDetailAgent(null)}
        output={liveOutput as ResourceRecommendationOutput | null}
        message={currentMessage}
        isRunning={isRunning}
      />
    );
  }

  if (selectedDetailAgent === 'study_buddy') {
    const liveOutput = parseAgentContent(agentTrace.study_buddy?.content);
    const currentMessage = [...messages]
      .reverse()
      .find((message) => message.role === 'user')?.content;
    const isRunning =
      !liveOutput &&
      (currentAgent === 'study_buddy' ||
        currentTurn?.agentTimeline.some(
          (item) => item.agentName === 'study_buddy' && item.status === 'running',
        ) === true);

    return (
      <StudyBuddyFlow
        onBack={() => setSelectedDetailAgent(null)}
        onClose={() => setSelectedDetailAgent(null)}
        output={liveOutput as StudyBuddyOutput | null}
        message={currentMessage}
        isRunning={isRunning}
      />
    );
  }

  const name = selectedDetailAgent;
  const cfg = AGENT_CONFIGS[name];
  if (!cfg) return null;

  const Icon = getIcon(cfg.icon);
  const traceEntry = agentTrace[name];
  const parsedOutput = parseAgentContent(traceEntry?.content);
  const highlightFields = AGENT_HIGHLIGHT_FIELDS[name] ?? [];

  // 兜底:highlightFields 没覆盖到的顶层字段,以 K-V 显示在最后
  const extraFields: { label: string; value: string }[] = [];
  if (parsedOutput) {
    const coveredKeys = new Set(highlightFields.map((f) => f.key));
    for (const [k, v] of Object.entries(parsedOutput)) {
      if (coveredKeys.has(k)) continue;
      const vStr =
        typeof v === 'string'
          ? v
          : Array.isArray(v)
            ? `[${v.length}]`
            : typeof v === 'object' && v !== null
              ? '{…}'
              : String(v);
      // 字符串过长截断,保持抽屉排版整洁
      extraFields.push({ label: k, value: vStr.length > 24 ? `${vStr.slice(0, 24)}…` : vStr });
    }
  }

  return (
    <div className="absolute inset-0 z-30 flex flex-col bg-bg-elevated animate-slide-in-right">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border-subtle px-4 py-3">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-md border border-border-subtle bg-bg-base text-text-secondary">
            <Icon size={16} />
          </div>
          <div>
            <h3 className="text-18 font-display font-semibold tracking-tight text-text-primary">
              {cfg.displayName}
            </h3>
            <p className="font-mono text-11 text-text-tertiary">
              v{cfg.version} · {name}
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => setSelectedDetailAgent(null)}
          className="rounded-md p-1.5 text-text-tertiary transition-colors hover:bg-bg-base hover:text-text-primary"
          aria-label="关闭详情"
        >
          <X size={16} />
        </button>
      </div>

      {/* 主体 4 段,可滚动 */}
      <div className="flex-1 overflow-y-auto px-4 py-4 scrollbar-thin">
        {/* 段 1: 本轮输出 */}
        <section className="mb-5">
          <h4 className="mb-2 text-11 uppercase tracking-wide text-text-tertiary">本轮输出</h4>
          {parsedOutput ? (
            <div className="grid grid-cols-2 gap-2 rounded-md border border-border-subtle bg-bg-base p-3">
              {highlightFields.map((f) => {
                const raw = getValueByPath(parsedOutput, f.key);
                const value = f.format ? f.format(raw) : String(raw ?? '-');
                return (
                  <div key={f.key} className="flex flex-col gap-0.5">
                    <span className="font-mono text-11 uppercase tracking-wide text-text-tertiary">
                      {f.label}
                    </span>
                    <span className="font-mono text-12 text-text-primary tabular-nums">{value}</span>
                  </div>
                );
              })}
              {extraFields.map((f) => (
                <div key={f.label} className="flex flex-col gap-0.5">
                  <span className="font-mono text-11 uppercase tracking-wide text-text-tertiary">
                    {f.label}
                  </span>
                  <span className="font-mono text-12 text-text-secondary tabular-nums">{f.value}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-12 italic text-text-tertiary">本轮暂未执行 / 无输出数据</p>
          )}
        </section>

        {/* 段 2: LLM 配置 */}
        <section className="mb-5">
          <h4 className="mb-2 text-11 uppercase tracking-wide text-text-tertiary">LLM 配置</h4>
          <div className="grid grid-cols-3 gap-2 rounded-md border border-border-subtle bg-bg-base p-3">
            {[
              { label: 'MODEL', value: cfg.llmConfig.model },
              { label: 'TEMPERATURE', value: cfg.llmConfig.temperature.toString() },
              { label: 'MAX TOKENS', value: cfg.llmConfig.maxTokens.toString() },
              { label: 'TIMEOUT', value: `${cfg.llmConfig.timeout}s` },
              { label: 'RETRIES', value: cfg.llmConfig.maxRetries.toString() },
              { label: 'THINKING', value: cfg.llmConfig.thinking ? 'on' : 'off' },
            ].map((item) => (
              <div key={item.label} className="flex flex-col gap-0.5">
                <span className="font-mono text-11 uppercase tracking-wide text-text-tertiary">
                  {item.label}
                </span>
                <span className="font-mono text-12 text-text-primary tabular-nums">
                  {item.value}
                </span>
              </div>
            ))}
          </div>
        </section>

        {/* 段 3: Prompt 摘要 */}
        <section className="mb-5">
          <h4 className="mb-2 text-11 uppercase tracking-wide text-text-tertiary">Prompt 摘要</h4>
          <p className="rounded-md border border-border-subtle bg-bg-base p-3 text-13 leading-relaxed text-text-secondary">
            {cfg.promptSummary}
          </p>
        </section>

        {/* 段 4: Thinking Process */}
        {cfg.thinkingProcess?.stages && cfg.thinkingProcess.stages.length > 0 && (
          <section className="mb-5">
            <h4 className="mb-2 flex items-center gap-2 text-11 uppercase tracking-wide text-text-tertiary">
              Thinking Process
              <span className="text-11 normal-case tracking-normal text-text-tertiary/70">· 参考流程,非实时</span>
            </h4>
            <ol className="space-y-2">
              {cfg.thinkingProcess.stages.map((stage, i) => (
                <li
                  key={i}
                  className="flex gap-2 rounded-md border border-border-subtle bg-bg-base p-2.5"
                >
                  <span className="font-mono text-12 font-medium text-text-secondary">
                    {String(i + 1).padStart(2, '0')}
                  </span>
                  <div className="flex-1">
                    <p className="text-12 font-medium text-text-primary">{stage.name}</p>
                    <p className="mt-0.5 text-11 leading-relaxed text-text-secondary">
                      {stage.description}
                    </p>
                  </div>
                </li>
              ))}
            </ol>
          </section>
        )}
      </div>
    </div>
  );
}

export default AgentDetailDrawer;
