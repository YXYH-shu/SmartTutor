/**
 * Agent configuration data derived from backend config/prompts/*.yaml
 * Initially hardcoded; can be migrated to API-sourced data later.
 */

export interface AgentLLMConfig {
  model: string;
  temperature: number;
  maxTokens: number;
  timeout: number;
  maxRetries: number;
  thinking: boolean;
}

export interface AgentConfig {
  name: string;
  displayName: string;
  description: string;
  version: string;
  icon: string;
  color: string;
  llmConfig: AgentLLMConfig;
  inputSchema: Record<string, unknown>;
  outputSchema: Record<string, unknown>;
  promptSummary: string;
  thinkingProcess?: {
    stages: { name: string; description: string }[];
  };
  designNotes?: string;
}

/**
 * Map from graph node names (used in SSE thinking steps) to agent config keys.
 */
export const NODE_TO_AGENT: Record<string, string> = {
  emotion_preprocess: 'emotion_analyzer',
  execute_stage: '_stage_agents',
  execute_agent: '_free_agents',
};

export const AGENT_CONFIGS: Record<string, AgentConfig> = {
  emotion_analyzer: {
    name: 'emotion_analyzer',
    displayName: '情感分析',
    description: '情感分析与学习状态评估智能体',
    version: '1.0',
    icon: 'Heart',
    color: 'rose',
    llmConfig: {
      model: 'glm-5',
      temperature: 0.4,
      maxTokens: 4028,
      timeout: 60,
      maxRetries: 2,
      thinking: true,
    },
    thinkingProcess: {
      stages: [
        { name: '情感识别', description: '分析学生消息中的情感倾向和情绪类型' },
        { name: '强度评估', description: '量化情感强度 (0-1)，识别情绪激烈程度' },
        { name: '趋势分析', description: '追踪情绪变化趋势：改善、稳定或下降' },
        { name: '学习意愿', description: '评估学生当前的学习意愿和动机水平' },
        { name: '回复语气', description: '推荐最佳回复语气风格，如鼓励、引导、严肃等' },
      ],
    },
    designNotes: '基于 GLM-5 大语言模型，通过多阶段链式思考（Chain-of-Thought）实现情感分析。未来将替换为专门微调的情感理解模型，通过 thinking 模式展示内部推理过程。',
    inputSchema: {
      type: 'object',
      properties: {
        message_history: {
          type: 'array',
          items: {
            type: 'object',
            properties: {
              role: { type: 'string' },
              content: { type: 'string' },
            },
          },
        },
        current_message: { type: 'string' },
      },
      required: ['message_history', 'current_message'],
    },
    outputSchema: {
      type: 'object',
      properties: {
        emotion: { type: 'string', description: '当前主要情绪' },
        intensity: { type: 'number', minimum: 0, maximum: 1 },
        trend: { type: 'string', enum: ['improving', 'stable', 'declining'] },
        learning_intent: { type: 'string', description: '学习意愿评估' },
        suggested_response_tone: { type: 'string', description: '建议回复语气' },
      },
      required: ['emotion', 'intensity', 'trend', 'learning_intent', 'suggested_response_tone'],
    },
    promptSummary: '分析学生的情感状态、学习意愿和情绪变化趋势，为后续智能体提供情感上下文，并建议最佳回复语气风格。',
  },

  safety_monitor: {
    name: 'safety_monitor',
    displayName: '安全监测',
    description: '内容安全检测与过滤智能体',
    version: '1.0',
    icon: 'Shield',
    color: 'amber',
    llmConfig: { model: 'glm-5', temperature: 0.1, maxTokens: 4028, timeout: 60, maxRetries: 2, thinking: false },
    inputSchema: {},
    outputSchema: {},
    promptSummary: '通过 5 阶段安全管线（风险感知→意图识别→价值评估→教育引导→问题转化）检测和过滤内容，保障学生安全。',
  },

  cognitive_diagnosis: {
    name: 'cognitive_diagnosis',
    displayName: '认知诊断',
    description: '知识掌握度评估与认知归因智能体',
    version: '3.0',
    icon: 'Brain',
    color: 'violet',
    llmConfig: { model: 'glm-5', temperature: 0.3, maxTokens: 4028, timeout: 120, maxRetries: 2, thinking: false },
    inputSchema: {},
    outputSchema: {},
    promptSummary: '评估学生对各知识点的掌握程度，生成认知归因分析，更新用户知识图谱和薄弱点。',
  },

  learning_path: {
    name: 'learning_path',
    displayName: '路径规划',
    description: '个性化学习路径规划智能体',
    version: '3.0',
    icon: 'Route',
    color: 'blue',
    llmConfig: { model: 'glm-5', temperature: 0.3, maxTokens: 4028, timeout: 120, maxRetries: 2, thinking: false },
    inputSchema: {},
    outputSchema: {},
    promptSummary: '基于认知诊断结果，规划 3-5 阶段个性化学习路径，含风险评估和纠偏建议。',
  },

  resource_recommender: {
    name: 'resource_recommender',
    displayName: '资源推荐',
    description: '自然语言风格资源推荐智能体',
    version: '3.0',
    icon: 'Library',
    color: 'emerald',
    llmConfig: { model: 'glm-5', temperature: 0.4, maxTokens: 4028, timeout: 60, maxRetries: 2, thinking: false },
    inputSchema: {},
    outputSchema: {},
    promptSummary: '推荐具体学习资源，关联知识点，提供学习建议和使用指南。',
  },

  study_buddy: {
    name: 'study_buddy',
    displayName: '学伴推荐',
    description: '自然语言风格学伴推荐智能体',
    version: '3.0',
    icon: 'Users',
    color: 'cyan',
    llmConfig: { model: 'glm-5', temperature: 0.5, maxTokens: 4028, timeout: 60, maxRetries: 2, thinking: false },
    inputSchema: {},
    outputSchema: {},
    promptSummary: '推荐适配的学习伙伴，分析互补原因，营造陪伴感和协作氛围。',
  },

  knowledge_responder: {
    name: 'knowledge_responder',
    displayName: '知识问答',
    description: '知识问答与内容响应智能体',
    version: '1.0',
    icon: 'BookOpen',
    color: 'indigo',
    llmConfig: { model: 'glm-5', temperature: 0.3, maxTokens: 4028, timeout: 60, maxRetries: 2, thinking: false },
    inputSchema: {},
    outputSchema: {},
    promptSummary: '解答学生的知识问题，生成清晰、准确、易懂的教学内容。',
  },

  content_polisher: {
    name: 'content_polisher',
    displayName: '内容润色',
    description: '教学内容矫正与润色智能体',
    version: '1.0',
    icon: 'Sparkles',
    color: 'pink',
    llmConfig: { model: 'glm-5', temperature: 0.3, maxTokens: 4028, timeout: 60, maxRetries: 2, thinking: false },
    inputSchema: {},
    outputSchema: {},
    promptSummary: '矫正和润色教学内容，提升表达清晰度、准确性和教学适切性。',
  },

  empathy_generator: {
    name: 'empathy_generator',
    displayName: '共情回复',
    description: '共情回复生成与心理支持智能体',
    version: '1.0',
    icon: 'HandHeart',
    color: 'orange',
    llmConfig: { model: 'glm-5', temperature: 0.5, maxTokens: 4028, timeout: 60, maxRetries: 2, thinking: false },
    inputSchema: {},
    outputSchema: {},
    promptSummary: '根据学生情感状态生成共情回复，提供心理支持和鼓励。',
  },
};

export const AGENT_DISPLAY_ORDER = [
  'emotion_analyzer',
  'safety_monitor',
  'cognitive_diagnosis',
  'learning_path',
  'resource_recommender',
  'study_buddy',
  'knowledge_responder',
  'content_polisher',
  'empathy_generator',
];
