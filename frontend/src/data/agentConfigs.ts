/**
 * Agent configuration data.
 *
 * 元数据来源:
 *  - description / version / promptSummary: 手抄自 backend/config/prompts/*.yaml
 *  - llmConfig: 手抄自各 agent yaml 的 model / temperature / max_tokens / thinking
 *  - thinkingProcess / designNotes: 从 prompt 模板和文档归纳
 *
 * 静态元数据仅用于侧边面板的"概览"展示。运行时实时数据(当前 agent 输出、
 * 思考步骤等)来自 SSE,见 useChatStore.thinkingSteps / agentTrace。
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
      maxTokens: 4096,
      timeout: 60,
      maxRetries: 2,
      thinking: false,
    },
    thinkingProcess: {
      stages: [
        { name: '情感识别', description: '分析学生消息中的情感倾向和情绪类型' },
        { name: '强度评估', description: '量化情感强度 (0-1),识别情绪激烈程度' },
        { name: '趋势分析', description: '追踪情绪变化趋势:改善、稳定或下降' },
        { name: '学习意愿', description: '评估学生当前的学习意愿和动机水平' },
        { name: '回复语气', description: '推荐最佳回复语气风格,如鼓励、引导、严肃等' },
      ],
    },
    designNotes:
      '基于 GLM-5 大语言模型,通过多阶段链式思考实现情感分析。每轮对话固定执行(emotion_preprocess 节点),结果写入 state.context 供所有后续 agent 读取。',
    inputSchema: {
      type: 'object',
      properties: {
        message_history: { type: 'array' },
        current_message: { type: 'string' },
      },
      required: ['message_history', 'current_message'],
    },
    outputSchema: {
      type: 'object',
      properties: {
        emotion: { type: 'string' },
        intensity: { type: 'number', minimum: 0, maximum: 1 },
        trend: { type: 'string', enum: ['improving', 'stable', 'declining'] },
        learning_intent: { type: 'string' },
        suggested_response_tone: { type: 'string' },
      },
      required: ['emotion', 'intensity', 'trend', 'learning_intent', 'suggested_response_tone'],
    },
    promptSummary:
      '分析学生的情感状态、学习意愿和情绪变化趋势,为后续智能体提供情感上下文,并建议最佳回复语气风格。',
  },

  safety_monitor: {
    name: 'safety_monitor',
    displayName: '安全监测',
    description: '内容安全检测与过滤智能体',
    version: '1.0',
    icon: 'Shield',
    color: 'amber',
    llmConfig: { model: 'glm-5', temperature: 0.1, maxTokens: 4096, timeout: 60, maxRetries: 2, thinking: false },
    thinkingProcess: {
      stages: [
        { name: 'Stage 1 风险感知', description: '检测是否存在安全风险,无风险直接放行(SAFE)' },
        { name: 'Stage 2 意图识别', description: '分类为科学好奇/情绪表达/边界试探/明确恶意' },
        { name: 'Stage 3 价值评估', description: '决定动作:TRANSFORM / SOFT_BLOCK / HARD_BLOCK / REFERRAL' },
        { name: 'Stage 4 教育引导', description: '主题映射 + 核心概念 + 学段适配(仅 TRANSFORM 路径)' },
        { name: 'Stage 5 问题转化', description: '语义锚定 + 操作剥离 + 引导嵌入(仅 TRANSFORM)' },
      ],
    },
    designNotes:
      '独立的安全检测代理,被 5 阶段安全管线(SafetyPipeline)内部调用,不直接参与 Workflow Stage 的智能体调度。每轮对话开始时由 safety_gate 固定节点自动执行。',
    inputSchema: {
      type: 'object',
      properties: {
        current_message: { type: 'string' },
        recent_messages: { type: 'array' },
      },
    },
    outputSchema: {
      type: 'object',
      properties: {
        risk_level: { type: 'string', enum: ['low', 'medium', 'high'] },
        action: { type: 'string', enum: ['SAFE', 'TRANSFORM', 'SOFT_BLOCK', 'HARD_BLOCK', 'REFERRAL'] },
        transformed_query: { type: 'string' },
        guidance: { type: 'string' },
      },
    },
    promptSummary:
      '通过 5 阶段安全管线检测和过滤内容,保障学生使用安全。危险内容拦截或转化,安全内容放行。',
  },

  cognitive_diagnosis: {
    name: 'cognitive_diagnosis',
    displayName: '认知诊断',
    description: '知识掌握度评估与认知归因智能体',
    version: '3.0',
    icon: 'Brain',
    color: 'violet',
    llmConfig: { model: 'glm-5', temperature: 0.3, maxTokens: 4096, timeout: 120, maxRetries: 2, thinking: false },
    thinkingProcess: {
      stages: [
        { name: '知识点提取', description: '从对话中识别学生涉及的知识点(15-25 个)' },
        { name: '掌握度评估', description: '为每个知识点生成掌握百分比 (0-100%)' },
        { name: '认知归因', description: '分析掌握度低/高的根本原因(根本概念/方法/应用)' },
        { name: '知识图谱构建', description: '生成节点 + 边(6 种关系:前置/相关/包含/应用/扩展/约束)' },
        { name: '薄弱点筛选', description: '识别需要重点关注的薄弱知识点' },
      ],
    },
    designNotes:
      '系统内唯一拥有自定义 post_process() 的 agent。执行后自动更新 UserProfile 的知识图谱、薄弱点和最后诊断时间。' +
      '集成模式(settings.kt.mode=integrated)下,先调用 services/kt-runtime-skill 的 REKT 模型拿真实掌握度,' +
      'LLM 仅做认知归因,数值字段不会幻觉。',
    inputSchema: {
      type: 'object',
      properties: {
        recent_messages: { type: 'array' },
        current_message: { type: 'string' },
        student_id: { type: 'string', description: '集成模式必填,用于调 KT runtime' },
        user_profile: { type: 'object' },
      },
    },
    outputSchema: {
      type: 'object',
      properties: {
        knowledge_states: { type: 'array', description: '15-25 个知识点掌握度列表' },
        mastery_rates: { type: 'object', description: 'skill_id → 0..1' },
        weak_points: { type: 'array' },
        knowledge_graph: { type: 'object' },
        diagnosis_source: { type: 'string', enum: ['llm_simulated', 'kt_rekt'] },
      },
    },
    promptSummary:
      '评估学生对各知识点的掌握程度,生成认知归因分析,更新用户知识图谱和薄弱点。',
  },

  learning_path: {
    name: 'learning_path',
    displayName: '路径规划',
    description: '个性化学习路径规划智能体',
    version: '3.0',
    icon: 'Route',
    color: 'blue',
    llmConfig: { model: 'glm-5', temperature: 0.3, maxTokens: 4096, timeout: 120, maxRetries: 2, thinking: false },
    thinkingProcess: {
      stages: [
        { name: '诊断解读', description: '基于 cognitive_diagnosis 输出的 mastery_rates 和 knowledge_graph' },
        { name: '阶段划分', description: '规划 3-5 个学习阶段,每阶段有明确目标' },
        { name: '资源匹配', description: '为每阶段匹配技能点、检查点和资源' },
        { name: '风险评估', description: '预测每阶段可能的学习障碍' },
        { name: '纠偏规则', description: '生成 adaptive_rules,定义出现偏差时的调整策略' },
      ],
    },
    designNotes:
      '强依赖 cognitive_diagnosis 的输出(diagnosis_result + knowledge_graph)。在 diagnosis_and_plan、collaboration_guide、path_adjustment 等 stage 中运行。',
    inputSchema: {
      type: 'object',
      properties: {
        diagnosis_result: { type: 'object' },
        knowledge_graph: { type: 'object' },
        goal: { type: 'string' },
        time_available: { type: 'string' },
      },
    },
    outputSchema: {
      type: 'object',
      properties: {
        planning_rationale: { type: 'string' },
        stages: { type: 'array', description: '3-5 个学习阶段' },
        adaptive_rules: { type: 'object' },
        estimated_completion: { type: 'string' },
      },
    },
    promptSummary:
      '基于认知诊断结果规划 3-5 阶段个性化学习路径,含风险评估和纠偏建议。',
  },

  resource_recommender: {
    name: 'resource_recommender',
    displayName: '资源推荐',
    description: '个性化学习资源推荐智能体(CTR 排序)',
    version: '3.0',
    icon: 'Library',
    color: 'emerald',
    llmConfig: { model: 'glm-5', temperature: 0.4, maxTokens: 4096, timeout: 60, maxRetries: 2, thinking: false },
    thinkingProcess: {
      stages: [
        { name: 'Plan 规划', description: 'LLM 生成召回-排序-混排的整体计划(选择哪些 tool)' },
        { name: 'Recall 召回', description: '通过 CandidateStore / SqlRetrieval / ItemCF 工具召回候选资源' },
        { name: 'Rank 排序', description: '调用 backend/algorithm 的 CTR ranking model(model.pt)对候选打分' },
        { name: 'Reflection 反思', description: 'LLM 检查推荐是否覆盖学生需求,若不足则补充召回' },
        { name: 'Summary 汇总', description: 'LLM 生成自然语言推荐文本 + 结构化资源列表' },
      ],
    },
    designNotes:
      '已集成真实 CTR ranking 模型(课题 4.2)。LLM 通过 plan/tool calling 模式调度召回和排序工具,' +
      '推荐结果来自真实模型打分而非 LLM 模拟。SQL 检索工具带白名单 + 黑名单 + session 级只读保护。',
    inputSchema: {
      type: 'object',
      properties: {
        diagnosis_result: { type: 'object' },
        target_knowledge: { type: 'string' },
        difficulty: { type: 'string' },
        learning_style: { type: 'string' },
      },
    },
    outputSchema: {
      type: 'object',
      properties: {
        recommendation_text: { type: 'string' },
        resources: { type: 'array', description: '结构化资源列表,含 title/type/knowledge_tags/learning_advice' },
        rationale: { type: 'string' },
      },
    },
    promptSummary:
      '调用真实 CTR 模型打分推荐学习资源,关联知识点,提供学习建议和使用指南。',
  },

  study_buddy: {
    name: 'study_buddy',
    displayName: '学伴推荐',
    description: '学伴匹配推荐智能体',
    version: '3.0',
    icon: 'Users',
    color: 'cyan',
    llmConfig: { model: 'glm-5', temperature: 0.5, maxTokens: 4096, timeout: 60, maxRetries: 2, thinking: false },
    thinkingProcess: {
      stages: [
        { name: '需求解析', description: '理解学生当前学习场景和学伴需求' },
        { name: '画像匹配', description: '基于 knowledge_graph 多维度匹配(互补/相似)' },
        { name: '风格互补', description: '学习风格、节奏、目标契合度分析' },
        { name: '小组编排', description: '生成 group_suggestion 含 formation_strategy' },
        { name: '联系方式', description: '推荐合适的接触方式(contact_suggestion)' },
      ],
    },
    designNotes:
      '当前通过 LLM 模拟多维度匹配,后续将接入真实学伴匹配算法(基于 learner_learner_relations 多维相似度)。',
    inputSchema: {
      type: 'object',
      properties: {
        user_graph: { type: 'object', description: '来自 cognitive_diagnosis 的 knowledge_graph' },
        topic: { type: 'string' },
      },
    },
    outputSchema: {
      type: 'object',
      properties: {
        recommendation_text: { type: 'string' },
        buddies: { type: 'array', description: '具体学伴列表,含 strengths/complement_score' },
        group_suggestion: { type: 'object' },
      },
    },
    promptSummary:
      '推荐适配的学习伙伴,分析互补原因,营造陪伴感和协作氛围。',
  },

  knowledge_responder: {
    name: 'knowledge_responder',
    displayName: '知识问答',
    description: '知识问答与内容响应智能体',
    version: '1.0',
    icon: 'BookOpen',
    color: 'indigo',
    llmConfig: { model: 'glm-5', temperature: 0.7, maxTokens: 4096, timeout: 60, maxRetries: 2, thinking: false },
    thinkingProcess: {
      stages: [
        { name: '上下文整合', description: '合并 diagnosis/resource/buddy/plan 等上下文' },
        { name: '内容生成', description: '根据 stage 角色生成自然语言回复' },
        { name: '语言组织', description: '调整语气、节奏、术语难度' },
      ],
    },
    designNotes:
      '核心内容生成 agent,几乎所有 stage 都会出现。temperature=0.7 是全系统最高,保证回复自然多样。' +
      '其输出通常成为 stage 内最终用户可见回复。',
    inputSchema: {
      type: 'object',
      properties: {
        diagnosis_result: { type: 'object' },
        resource_list: { type: 'array' },
        buddy_info: { type: 'object' },
        learning_plan: { type: 'object' },
      },
    },
    outputSchema: {
      type: 'object',
      properties: {
        response_text: { type: 'string' },
      },
    },
    promptSummary:
      '根据 stage 和上下文生成自然语言回复,是 stage 内核心内容生产者。',
  },

  content_polisher: {
    name: 'content_polisher',
    displayName: '内容润色',
    description: '教学内容矫正与润色智能体',
    version: '1.0',
    icon: 'Sparkles',
    color: 'pink',
    llmConfig: { model: 'glm-5', temperature: 0.4, maxTokens: 4096, timeout: 60, maxRetries: 2, thinking: false },
    thinkingProcess: {
      stages: [
        { name: '科学准确性', description: '检查事实、概念、术语是否正确' },
        { name: '语言清晰度', description: '优化表达,避免歧义和冗余' },
        { name: '角色一致性', description: '保持教师人设的语气和立场' },
        { name: '情感基调', description: '确保支持、鼓励、不评判的基调' },
      ],
    },
    designNotes:
      '通常在 knowledge_responder 之后运行,作为 stage 内的"质量保障"环节。接收前一个 agent 的输出作为 content,产出 polished_content。',
    inputSchema: {
      type: 'object',
      properties: {
        content: { type: 'string', description: '前一个 agent 的输出文本' },
      },
    },
    outputSchema: {
      type: 'object',
      properties: {
        polished_content: { type: 'string' },
        corrections_made: { type: 'array' },
      },
    },
    promptSummary:
      '矫正和润色教学内容,提升表达清晰度、准确性和教学适切性。',
  },

  empathy_generator: {
    name: 'empathy_generator',
    displayName: '共情回复',
    description: '共情回复生成与心理支持智能体',
    version: '1.0',
    icon: 'HandHeart',
    color: 'orange',
    llmConfig: { model: 'glm-5', temperature: 0.6, maxTokens: 4096, timeout: 60, maxRetries: 2, thinking: false },
    thinkingProcess: {
      stages: [
        { name: '情感读取', description: '从 emotion_state 识别学生情绪和强度' },
        { name: '技巧选择', description: '匹配心理支持技巧(积极倾听/共情/正常化/重构等)' },
        { name: '内容融合', description: '在原始回复中融入共情语言,不扭曲事实信息' },
        { name: '人设强化', description: '生成 teacher_persona 描述,确保一致性' },
      ],
    },
    designNotes:
      '通常作为 stage 内最后一个 agent。也作为 response_assembler 节点的回退机制(当 final_response 为空时自动调用)。',
    inputSchema: {
      type: 'object',
      properties: {
        raw_response: { type: 'string' },
        emotion_state: { type: 'object' },
        user_profile: { type: 'object' },
      },
    },
    outputSchema: {
      type: 'object',
      properties: {
        empathetic_response: { type: 'string' },
        psychological_techniques: { type: 'array' },
        teacher_persona: { type: 'string' },
      },
    },
    promptSummary:
      '根据学生情感状态生成共情回复,提供心理支持和鼓励,不扭曲原始信息。',
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
