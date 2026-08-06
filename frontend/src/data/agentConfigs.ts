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

const RUNTIME_LLM_MODEL = import.meta.env.VITE_LLM_MODEL || 'glm-4-flash';

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
      '基于 DeepSeek V4 Flash 大语言模型进行情感分析。每轮对话固定执行(emotion_preprocess 节点),结果写入 state.context 供所有后续 agent 读取。',
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
    description: '风险与意图识别、三分支决策及安全教育引导智能体',
    version: '3.0',
    icon: 'Shield',
    color: 'amber',
    llmConfig: { model: RUNTIME_LLM_MODEL, temperature: 0.1, maxTokens: 4096, timeout: 60, maxRetries: 2, thinking: false },
    thinkingProcess: {
      stages: [
        { name: '风险与意图识别', description: '联合识别风险类别、用户意图、可执行性、重复试探和危机信号' },
        { name: '三分支价值评估', description: '按确定性规则选择 PASS / REJECT / GUIDE' },
        { name: '两轮学科化转化', description: '仅 GUIDE 调用 Skill：第一轮选择相关科目，第二轮在该科目内完善具体学习问题' },
      ],
    },
    designNotes:
      '每轮对话先由 safety_gate 固定执行。PASS 进入教育智能体链路；REJECT 直接返回拒绝或危机关怀；GUIDE 调用独立 Skill。存在多个强相关科目时，先让学生选择科目，再选择该科目内的具体知识焦点；只有一个相关科目时保留单轮选择。',
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
        branch: { type: 'string', enum: ['PASS', 'REJECT', 'GUIDE'] },
        risk_category: { type: 'string', enum: ['N', 'A', 'B', 'C', 'D1', 'D2', 'D3'] },
        intent: { type: 'string', enum: ['learning', 'emotional', 'probing', 'malicious'] },
        reject_type: { type: 'string' },
        safe_query: { type: 'string' },
        selection_mode: { type: 'string', enum: ['two_stage'] },
        school_subject: { type: 'string' },
        subject_focus: { type: 'string' },
        subject_options: { type: 'array', minItems: 2, maxItems: 3 },
        learning_options: { type: 'array', minItems: 2, maxItems: 3 },
        recommended_option: { type: 'string' },
        preserved_elements: { type: 'array' },
      },
    },
    promptSummary:
      '联合识别风险与意图，通过确定性规则分为直接放行、直接拒绝、教育引导三个分支；教育引导由独立 Skill 通过“科目选择→知识焦点选择”逐步完善问题。',
  },

  cognitive_diagnosis: {
    name: 'cognitive_diagnosis',
    displayName: '认知诊断',
    description: '知识掌握度评估与认知归因智能体',
    version: '3.0',
    icon: 'Brain',
    color: 'violet',
    llmConfig: { model: 'glm-5', temperature: 0.3, maxTokens: 16384, timeout: 180, maxRetries: 3, thinking: true },
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
    color: 'gold',
    llmConfig: { model: 'glm-5', temperature: 0.5, maxTokens: 16384, timeout: 180, maxRetries: 3, thinking: true },
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
        learning_path: { type: 'array', description: '后端原生 5 阶段路径' },
        stages: { type: 'array', description: '3-5 个学习阶段' },
        recommended_questions: { type: 'array', description: 'LPP Runtime 固定 P1-P5 推荐题' },
        adaptive_rules: { type: 'string' },
        total_estimated_time: { type: 'string' },
        estimated_completion: { type: 'string' },
      },
    },
    promptSummary:
      '基于认知诊断结果规划 3-5 阶段个性化学习路径,含风险评估和纠偏建议。',
  },

  resource_recommender: {
    name: 'resource_recommender',
    displayName: '资源推荐',
    description: '个性化学习资源推荐智能体(图模型排序)',
    version: '4.0',
    icon: 'Library',
    color: 'emerald',
    llmConfig: { model: 'glm-5', temperature: 0.4, maxTokens: 4028, timeout: 180, maxRetries: 2, thinking: false },
    thinkingProcess: {
      stages: [
        { name: 'Plan 规划', description: 'LLM 仅规划 SQL 召回和两种排序方式' },
        { name: 'Recall 召回', description: '通过 SqlRetrievalTool 召回候选；缺失时使用资源全集' },
        { name: 'Rank 排序', description: '使用异构 GAT 个性化排序，或按冻结文本向量计算资源相似度' },
        { name: 'Reflection 反思', description: 'LLM 检查推荐是否覆盖学生需求,若不足则补充召回' },
        { name: 'Summary 汇总', description: 'LLM 生成自然语言推荐文本 + 结构化资源列表' },
      ],
    },
    designNotes:
      '已集成异构图推荐模型。LLM 通过 plan/tool calling 模式调度 SQL 召回和排序工具，' +
      '个性化结果来自图模型分数，资源相似度来自冻结文本向量。SQL 检索带白名单、黑名单和会话级只读保护。',
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
      '调用异构图模型个性化排序，或按文本语义相似度推荐相关学习资源。',
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

  content_corrector: {
    name: 'content_corrector',
    displayName: '内容矫正',
    description: '末端教育内容验收：直接输出、局部修改或退回重写',
    version: '2.0',
    icon: 'Sparkles',
    color: 'blue',
    llmConfig: { model: RUNTIME_LLM_MODEL, temperature: 0, maxTokens: 4096, timeout: 60, maxRetries: 2, thinking: false },
    thinkingProcess: {
      stages: [
        { name: '四项验收', description: '检查科学可靠性、教育完整性、结构清晰度和内容安全性' },
        { name: '动作判定', description: '在 PASS、PATCH、REGENERATE 三种动作中选择' },
        { name: '局部修改保护', description: 'PATCH 不得明显缩短内容或破坏标题、编号和列表' },
        { name: '退回重写', description: '严重缺项时将问题清单退回知识回复智能体，最多一次' },
      ],
    },
    designNotes:
      '不处理情感，也不生成整篇内容。PASS 逐字输出；PATCH 仅局部修改；REGENERATE 退回 knowledge_responder 完整重写一次。REJECT/GUIDE 安全回复不经过此节点。',
    inputSchema: {
      type: 'object',
      properties: {
        original_response: { type: 'string' },
        student_question: { type: 'string' },
        subject: { type: 'string' },
        grade_level: { type: 'string' },
        conversation_stage: { type: 'string' },
        safety_constraints: { type: 'object' },
      },
      required: ['original_response'],
    },
    outputSchema: {
      type: 'object',
      properties: {
        action: { type: 'string', enum: ['PASS', 'PATCH', 'REGENERATE'] },
        issues: { type: 'array' },
        patched_response: { type: 'string' },
        checks: { type: 'object' },
      },
      required: ['action', 'issues', 'patched_response', 'checks'],
    },
    promptSummary:
      '验收最终回答：合格直接输出，局部问题小修，严重缺项退回知识回复智能体重写。',
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
  'content_polisher',
  'empathy_generator',
  'content_corrector',
];

/**
 * 每个 agent 在 Hero Slot / 详情抽屉里要重点展示的"本轮实际输出"字段。
 * key 是 agent 内部名,值是要从 agentTrace[name].content(JSON)里提取的字段。
 * format 函数把原始值转成短字符串;不传则直接 String()。
 */
export interface HighlightFieldDef {
  key: string;          // 顶层字段名(支持点路径,如 'a.b')
  label: string;        // 中文标签
  format?: (v: unknown) => string;
}

export const AGENT_HIGHLIGHT_FIELDS: Record<string, HighlightFieldDef[]> = {
  emotion_analyzer: [
    { key: 'emotion', label: '情绪' },
    {
      key: 'intensity',
      label: '强度',
      format: (v) => (typeof v === 'number' ? `${Math.round(v * 100)}%` : '-'),
    },
    { key: 'trend', label: '趋势' },
  ],
  cognitive_diagnosis: [
    {
      key: 'diagnosis_source',
      label: '数据来源',
      format: (v: unknown) =>
        v === 'kt_rekt'
          ? '真实KT模型'
          : typeof v === 'string'
            ? v
            : 'LLM模拟',
    },
    {
      key: 'weak_points',
      label: '薄弱点',
      format: (v) => {
        if (!Array.isArray(v)) return '-';
        const names = v.slice(0, 2).map((item: any) =>
          typeof item === 'object' && item !== null ? (item.skill_name || item.skill_id || '未命名') : String(item),
        );
        return names.length > 0 ? `${names.join('、')} (${v.length} 个)` : '-';
      },
    },
    { key: 'knowledge_states', label: '知识点', format: (v: unknown) => (Array.isArray(v) ? `${v.length} 个` : '-') },
    {
      key: 'diagnosis_summary',
      label: '诊断总结',
      format: (v: unknown) => (typeof v === 'string' ? (v.length > 60 ? `${v.slice(0, 60)}…` : v) : '-'),
    },
    {
      key: 'mastery_rates',
      label: '掌握度',
      format: (v: unknown) => {
        if (typeof v !== 'object' || v === null) return '-';
        const entries = Object.entries(v as Record<string, number>).slice(0, 3);
        return entries.map(([k, val]) => `${k}: ${(val * 100).toFixed(0)}%`).join(' / ') || '-';
      },
    },
  ],
  learning_path: [
    {
      key: 'recommended_questions',
      label: '推荐序列',
      format: (v) => {
        if (!Array.isArray(v)) return '-';
        const ids = v.slice(0, 5).map((item: any, index: number) => {
          const questionId = typeof item === 'object' && item !== null ? item.question_id : undefined;
          return `P${index + 1}${questionId !== undefined ? `(#${questionId})` : ''}`;
        });
        return ids.length > 0 ? ids.join(' → ') : '-';
      },
    },
    {
      key: 'stages',
      label: '学习阶段',
      format: (v) => {
        if (!Array.isArray(v)) return '-';
        const names = v.slice(0, 2).map((item: any, i: number) =>
          typeof item === 'object' && item !== null ? (item.name || item.stage_name || `阶段${i + 1}`) : String(item),
        );
        return names.length > 0 ? `${names.join('、')} (${v.length} 阶段)` : '-';
      },
    },
    {
      key: 'planning_rationale',
      label: '规划依据',
      format: (v) => (typeof v === 'string' ? (v.length > 40 ? `${v.slice(0, 40)}…` : v) : '-'),
    },
  ],
  resource_recommender: [
    {
      key: 'resources',
      label: '推荐资源',
      format: (v) => {
        if (!Array.isArray(v)) return '-';
        const titles = v.slice(0, 2).map((item: any) =>
          typeof item === 'object' && item !== null ? (item.title || item.name || '未命名') : String(item),
        );
        return titles.length > 0 ? `${titles.join('、')} (${v.length} 个)` : '-';
      },
    },
    {
      key: 'recommendation_text',
      label: '推荐语',
      format: (v) => (typeof v === 'string' ? (v.length > 40 ? `${v.slice(0, 40)}…` : v) : '-'),
    },
    {
      key: 'resources.0.graph_score',
      label: '图模型分数',
      format: (v: unknown) => (typeof v === 'number' ? v.toFixed(4) : '无图分数'),
    },
    {
      key: 'planning.recall_strategy',
      label: '召回策略',
      format: (v: unknown) => (typeof v === 'string' ? (v.length > 20 ? `${v.slice(0, 20)}…` : v) : '-'),
    },
    {
      key: 'planning.target_count',
      label: '目标数',
      format: (v: unknown) => (typeof v === 'number' ? String(v) : '-'),
    },
    {
      key: 'reflection.coverage_score',
      label: '覆盖度',
      format: (v: unknown) => (typeof v === 'number' ? `${(v * 100).toFixed(0)}%` : '-'),
    },
    {
      key: 'reflection.passed',
      label: '反思通过',
      format: (v: unknown) => (v === true ? '是' : v === false ? '否' : '-'),
    },
    {
      key: 'tool_trace',
      label: '工具轨迹',
      format: (v: unknown) => (Array.isArray(v) ? `${v.length} 步` : '-'),
    },
    {
      key: 'plan_history',
      label: '规划轮数',
      format: (v: unknown) => (Array.isArray(v) ? `${v.length} 轮` : '-'),
    },
    {
      key: 'reflection_history',
      label: '反思轮数',
      format: (v: unknown) => (Array.isArray(v) ? `${v.length} 轮` : '-'),
    },
  ],
  study_buddy: [
    {
      key: 'buddies',
      label: '候选学伴',
      format: (v) => {
        if (!Array.isArray(v)) return '-';
        const names = v.slice(0, 2).map((item: any) =>
          typeof item === 'object' && item !== null ? (item.name || item.username || '匿名') : String(item),
        );
        return names.length > 0 ? `${names.join('、')} (${v.length} 位)` : '-';
      },
    },
    {
      key: 'recommendation_text',
      label: '推荐语',
      format: (v) => (typeof v === 'string' ? (v.length > 40 ? `${v.slice(0, 40)}…` : v) : '-'),
    },
  ],
  empathy_generator: [
    {
      key: 'psychological_techniques',
      label: '心理技巧',
      format: (v) => (Array.isArray(v) ? v.slice(0, 3).join('、') : '-'),
    },
    {
      key: 'empathetic_response',
      label: '回复预览',
      format: (v) => (typeof v === 'string' ? (v.length > 40 ? `${v.slice(0, 40)}…` : v) : '-'),
    },
  ],
  content_polisher: [
    { key: 'corrections_made', label: '矫正项', format: (v) => (Array.isArray(v) ? `${v.length} 项` : '-') },
    {
      key: 'polished_content',
      label: '润色预览',
      format: (v) => (typeof v === 'string' ? (v.length > 40 ? `${v.slice(0, 40)}…` : v) : '-'),
    },
  ],
  content_corrector: [
    {
      key: 'action',
      label: '验收动作',
    },
    {
      key: 'status',
      label: '处理状态',
    },
    {
      key: 'issues',
      label: '发现问题',
      format: (v: unknown) => (Array.isArray(v) ? `${v.length} 项` : '0 项'),
    },
    {
      key: 'structure_preserved',
      label: '结构保留',
      format: (v: unknown) => (v === true ? '是' : '否'),
    },
  ],
  safety_monitor: [
    { key: 'branch', label: '处理分支' },
    { key: 'raw_branch', label: '分支代码' },
    { key: 'safety_context.risk_category', label: '风险类别' },
    { key: 'safety_context.intent', label: '识别意图' },
    { key: 'safety_context.reject_type', label: '拒绝原因' },
    { key: 'safety_context.guidance_skill.selection_phase', label: '选择阶段' },
    { key: 'safety_context.guidance_skill.school_subject', label: '主科目' },
    { key: 'safety_context.guidance_skill.subject_focus', label: '知识焦点' },
    {
      key: 'safety_context.guidance_skill.learning_options',
      label: '学习方向',
      format: (v) => (Array.isArray(v) ? `${v.length} 个选项` : '-'),
    },
  ],
};
