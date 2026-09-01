/**
 * Agent 元数据服务:拉取后端各 agent 真实生效的 LLM 配置。
 *
 * 端点: GET /api/v1/agents/configs(无鉴权)
 * 用途: 就地覆盖 AGENT_CONFIGS 里手抄的静态 llmConfig,
 *       让智能体卡片(AgentStudio)和详情抽屉(AgentDetailDrawer)展示真实值。
 * 失败时静默回退静态值(仅 console.warn,不抛错、不弹 UI)。
 */
import api from './api';
import { AGENT_CONFIGS, type AgentConfig } from '@/data/agentConfigs';

/** 对齐后端 AgentConfigResponse(app/api/schemas.py) */
export interface AgentLlmConfigResponse {
  agent: string;
  model: string;
  base_url: string;
  temperature: number;
  max_tokens: number;
  thinking: boolean;
  timeout: number;
  max_retries: number;
}

// 模块级缓存:页面生命周期内只请求一次(StrictMode 双挂载也只发一次)
let configsPromise: Promise<AgentLlmConfigResponse[]> | null = null;

function fetchAgentLlmConfigs(): Promise<AgentLlmConfigResponse[]> {
  configsPromise ??= api
    .get<AgentLlmConfigResponse[]>('/api/v1/agents/configs')
    .then((res) => res.data);
  return configsPromise;
}

/**
 * 拉取后端配置并就地覆盖 AGENT_CONFIGS[name].llmConfig。
 * 前端没有的 agent(如 knowledge_responder)直接跳过,保留各自静态值。
 * 返回是否成功应用。
 */
export async function applyRuntimeLlmConfigs(): Promise<boolean> {
  let configs: AgentLlmConfigResponse[];
  try {
    configs = await fetchAgentLlmConfigs();
  } catch (err) {
    console.warn('[agent] 拉取后端 LLM 配置失败,回退静态 llmConfig', err);
    return false;
  }
  for (const item of configs) {
    const cfg: AgentConfig | undefined = AGENT_CONFIGS[item.agent];
    if (!cfg) continue;
    cfg.llmConfig = {
      ...cfg.llmConfig,
      model: item.model,
      baseUrl: item.base_url.replace(/\/+$/, ''),
      temperature: item.temperature,
      maxTokens: item.max_tokens,
      timeout: item.timeout,
      maxRetries: item.max_retries,
      thinking: item.thinking,
    };
  }
  return true;
}
