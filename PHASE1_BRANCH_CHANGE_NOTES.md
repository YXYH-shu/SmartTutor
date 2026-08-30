# 4.3 安全监测与内容矫正：第一阶段分支修改说明

## 修改范围

本阶段只修复安全监测智能体和内容矫正智能体的前端字段展示。未修改后端判断、提示词、LangGraph 路由、接口契约、数据库、模型配置和其他智能体。

## 安全监测智能体

### 工作原理

安全监测节点输出 `PASS / GUIDE / REJECT` 三种分支，并在 `safety_context` 中保存风险类别、识别意图、核心主题、是否索取操作性细节、分类判断来源以及教育引导结果。前端详情卡片只读取已有输出，不参与安全判断。

### 修改策略

- 保留处理分支、分支代码、风险类别和识别意图。
- 删除初次进入 GUIDE 时尚未产生或路径不正确的“选择阶段、主科目、知识焦点”。
- 改为展示始终由后端稳定产出的核心主题、操作性请求和判断来源。
- GUIDE 使用 `guidance_skill.selection_mode` 展示英文技术值 `TWO_STAGE`。
- 条件性字段不再显示 `-`：无拒绝时显示 `N/A`，无学习选项时显示 `NO_SELECTION_REQUIRED`。
- 中文字段标签保持不变，本阶段新增或转换的显示值统一使用英文技术值。

## 内容矫正智能体

### 工作原理

内容矫正节点对最终教学回答执行四项验收，输出 `PASS / PATCH / REGENERATE`。`PASS` 时 `patched_response` 按契约必须为空，`regeneration_count=0` 表示未触发重写，这些都是合法业务状态。

### 修改策略

- 同时展示模型建议动作和本地规则校验后的最终验收动作。
- 将内部状态代码规范为大写英文技术值。
- 将空问题列表显示为 `NO_ISSUES`。
- 汇总四项验收的通过数量。
- 将空修补文本显示为 `NO_PATCH_REQUIRED`。
- 将零次重写显示为 `NOT_TRIGGERED`。
- 不改变后端输出字段及验收逻辑。

## 公共文件修改明细

### 文件

`frontend/src/data/agentConfigs.ts`

修改后位置：`content_corrector` 配置约第 614～674 行，`safety_monitor` 配置约第 675～716 行。

该文件属于多个智能体共用的前端配置。本次只替换 `AGENT_HIGHLIGHT_FIELDS.content_corrector` 和 `AGENT_HIGHLIGHT_FIELDS.safety_monitor` 两个属性的代码，没有修改其他属性或通用渲染逻辑。

### 修改前代码

```ts
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
```

### 修改后代码

```ts
  content_corrector: [
    {
      key: 'action',
      label: '验收动作',
    },
    {
      key: 'requested_action',
      label: '模型建议',
    },
    {
      key: 'status',
      label: '处理状态',
      format: (v: unknown) => {
        const labels: Record<string, string> = {
          passed: 'PASSED',
          patched: 'PATCHED',
          audited: 'AUDITED',
          patch_rejected: 'PATCH_REJECTED',
          regeneration_limit: 'REGENERATION_LIMIT',
          audit_fallback: 'AUDIT_FALLBACK',
        };
        return typeof v === 'string' ? (labels[v] ?? v.toUpperCase()) : 'UNKNOWN';
      },
    },
    {
      key: 'issues',
      label: '发现问题',
      format: (v: unknown) =>
        Array.isArray(v) && v.length > 0 ? `${v.length} ISSUES` : 'NO_ISSUES',
    },
    {
      key: 'checks',
      label: '四项验收',
      format: (v: unknown) => {
        if (typeof v !== 'object' || v === null) return 'NO_CHECK_DETAILS';
        const values = Object.values(v as Record<string, unknown>);
        if (values.length === 0) return 'NO_CHECK_DETAILS';
        const passed = values.filter((item) => item === true).length;
        return `${passed}/${values.length} PASSED`;
      },
    },
    {
      key: 'patched_response',
      label: '修补结果',
      format: (v: unknown) =>
        typeof v === 'string' && v.trim()
          ? (v.length > 40 ? `${v.slice(0, 40)}…` : v)
          : 'NO_PATCH_REQUIRED',
    },
    {
      key: 'structure_preserved',
      label: '结构保留',
      format: (v: unknown) => (v === true ? 'YES' : v === false ? 'NO' : 'NOT_CHECKED'),
    },
    {
      key: 'regeneration_count',
      label: '重写次数',
      format: (v: unknown) =>
        typeof v === 'number' && v > 0
          ? `${v} ${v === 1 ? 'REWRITE' : 'REWRITES'}`
          : 'NOT_TRIGGERED',
    },
  ],
  safety_monitor: [
    { key: 'branch', label: '处理分支' },
    { key: 'raw_branch', label: '分支代码' },
    { key: 'safety_context.risk_category', label: '风险类别' },
    { key: 'safety_context.intent', label: '识别意图' },
    { key: 'safety_context.core_topic', label: '核心主题' },
    {
      key: 'safety_context.operational_request',
      label: '操作性请求',
      format: (v: unknown) => (v === true ? 'YES' : v === false ? 'NO' : 'UNKNOWN'),
    },
    {
      key: 'safety_context.classifier.decision_source',
      label: '判断来源',
      format: (v: unknown) => (typeof v === 'string' ? v.toUpperCase() : 'UNKNOWN'),
    },
    {
      key: 'safety_context.reject_type',
      label: '拒绝原因',
      format: (v: unknown) => (typeof v === 'string' && v ? v : 'N/A'),
    },
    {
      key: 'safety_context.guidance_skill.selection_mode',
      label: '引导方式',
      format: (v: unknown) => (v === 'two_stage' ? 'TWO_STAGE' : 'N/A'),
    },
    {
      key: 'safety_context.guidance_skill.learning_options',
      label: '学习方向',
      format: (v) =>
        Array.isArray(v) && v.length > 0 ? `${v.length} OPTIONS` : 'NO_SELECTION_REQUIRED',
    },
  ],
```

### 公共影响评估

- `AGENT_HIGHLIGHT_FIELDS` 只控制详情卡片的字段选择和文案格式，不参与智能体执行。
- 未修改 `HighlightFieldDef`、`AgentDetailDrawer`、`AgentStudio` 或字段读取函数。
- 未改变后端事件、状态字段和 API 返回。
- 未修改 `emotion_analyzer`、`cognitive_diagnosis`、`learning_path`、`resource_recommender`、`study_buddy`、`content_polisher`、`empathy_generator` 等配置。
- 因此不会改变其他智能体的调用、路由、输出或展示配置。

## 待总协调人员确认：LLM 配置展示是否改为运行时数据

### 问题说明

当前详情卡片中的 `MODEL / TEMPERATURE / MAX TOKENS / TIMEOUT / RETRIES / THINKING` 来自公共前端文件 `frontend/src/data/agentConfigs.ts` 的静态配置，并不是后端每次调用模型时返回的运行时数据。该文件顶部也注明 `llmConfig` 是从各智能体 YAML 手工抄录。因此，只要后端 YAML、环境变量或分阶段调用参数发生变化，前端卡片就可能继续显示旧值。

当前两个相关智能体存在以下展示差异：

| 智能体 | 前端静态显示 | 后端当前配置或实际调用 |
|---|---|---|
| `safety_monitor` | `glm-4-flash / 0.1 / 4096 / 60s / 2 / off` | 门面 YAML 为 `1800 / 60s / 2`；实际主分类器和独立复核器分别使用各自 YAML，当前单次 `max_tokens` 均为 `180` |
| `content_corrector` | `glm-4-flash / 0.0 / 4096 / 60s / 2 / off` | `content_corrector.yaml` 为 `glm-4-flash / 0.0 / 2048 / 60s / 1 / off` |

安全监测是多阶段管线，一个卡片内只有一组 LLM 参数，无法同时准确表示主分类器、独立复核器和教育引导 Skill。该问题只影响配置说明的可信度，不改变后端实际模型调用、安全判断、内容矫正结果或 LangGraph 路由。

### 可选处理方案

**方案 A：由后端提供运行时解析后的配置（推荐）**

- 后端在智能体执行事件或专用元数据接口中返回本次实际使用的 `model`、`temperature`、`max_tokens`、`timeout`、`max_retries` 和 `thinking`。
- 安全监测按 `primary_classifier`、`adjudicator`、`guidance_skill` 分阶段展示，不再用一组静态参数概括整个管线。
- 前端优先显示运行时数据；没有运行时数据时，再使用静态元数据作为说明性兜底。
- 该方案需要修改公共后端事件/API 契约和公共前端详情卡片，建议由总协调人员统一设计并覆盖所有智能体。

**方案 B：只同步当前静态数字**

- 将 `agentConfigs.ts` 中 `safety_monitor` 和 `content_corrector` 的静态值改成与当前 YAML 一致。
- 不修改接口，合并成本较低。
- 后端配置以后再次变化时仍可能出现不一致，且无法完整表达安全监测的多阶段参数。

### 本分支当前处理状态

本分支尚未实施上述任一方案，也没有修改公共接口。请总协调人员决定是否修改、采用哪一种方案，以及处理范围是所有智能体还是仅处理本分支新增的两个智能体。若采用方案 A，需要在合并前明确运行时字段名称和前端展示口径；若采用方案 B，只需同步静态元数据，但应在卡片中标注其为配置说明而非本次调用实测值。

## 验证

- TypeScript 语法与转译检查：通过。
- 完整前端构建：通过。
- 后端和模型调用：本阶段未修改后端，未执行模型调用。

## 智能体运行记录空值文案补充修改

### 公共文件

`frontend/src/components/chat/AgentInteractionLog.tsx`

该文件属于公共运行记录组件。本次修改通过智能体名称做定向判断，只改变 `safety_monitor` 和 `content_corrector` 的显示值，不修改全局 `jsonTree.tsx`，因此其他智能体仍沿用原有渲染逻辑。

### 安全监测修改

修改前：

```tsx
裁决原因：<b>{String(classifier.adjudication_reason ?? '无')}</b>
```

修改后：

```tsx
{hasAdjudicationReason ? '裁决原因' : '裁决状态'}：
<b>
  {hasAdjudicationReason ? String(adjudicationReason) : 'NOT_REQUIRED'}
</b>
```

实际触发独立复核时继续展示具体裁决原因；未触发时显示 `裁决状态：NOT_REQUIRED`，不再把“没有进行裁决”误写成一项空的裁决原因。

GUIDE 分支补充为面向教育过程的展示，不再把底层运行时异常作为主信息：

```text
处理方式：EDUCATIONAL_GUIDANCE_TRANSFORMATION_SKILL
转化状态：COMPLETED（Skill 异常时为 FALLBACK_COMPLETED）
触发来源：MODEL_CONTENT_FILTER 或 SAFETY_CLASSIFICATION
请求：METHOD_REQUEST / EDUCATIONAL_ANALYSIS / UNKNOWN
```

`PASS` 和 `REJECT` 分支仍保留裁决状态或具体裁决原因。该条件展示仍只作用于 `safety_monitor`。

### 内容矫正修改

新增仅对 `content_corrector` 生效的展示归一化：

```tsx
issues:
  Array.isArray(input.issues) && input.issues.length === 0
    ? 'NO_ISSUES'
    : input.issues,
patched_response:
  typeof input.patched_response === 'string' && !input.patched_response.trim()
    ? 'NO_PATCH_REQUIRED'
    : input.patched_response,
```

后端原始字段保持不变，只在渲染前生成显示副本：空问题列表显示 `NO_ISSUES`，无需修补时显示 `NO_PATCH_REQUIRED`。
