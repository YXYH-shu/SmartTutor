# KT 全局 Top-18 投影设计

## 目标

每次 KT 诊断从 REKT 的全量预测中，按 `kt-runtime-skill` 已有的上下文相关性选择逻辑选出 18 个知识点。SmartTutor 从该边界开始只保留、持久化、展示和传递这 18 个知识点；下游智能体不得再接触其余预测项。

## 边界与数据流

1. `run_kt_for_student` 不再关闭 skill 的分析报告，以获得其 `llm_analysis.selected_knowledge_points`。该字段已经由 `select_relevant_knowledge_points` 使用当前问题、历史上下文、近期交互和知识点描述选出最多 18 项。
2. `kt_integration._normalize_kt_output` 以这 18 个 `skill_id` 过滤 `predictions`，再构造 `knowledge_states`、`mastery_rates` 与 `weak_points`。因此认知诊断输出本身最多 18 项，而不是先产生 334 项再由消费者压缩。
3. `CognitiveDiagnosisAgent` 的 `finalize_output`、图上下文、学习路径、资源推荐、知识问答、前端诊断摘要都消费该同一份 18 项输出。
4. 用户画像中的 `knowledge_graph` 与 `weak_points` 用本轮 18 项覆盖式更新，不能把旧轮次的全量预测合并回来。仅保存这 18 项的掌握度映射；本轮生成的结构图若存在，也作为本轮数据保存。

## 失败与兼容策略

- KT skill 未返回选择结果时，使用有界的 18 项兜底并记录告警；绝不退回传递完整预测列表。
- 既有数据库中的历史执行日志不追溯删除；新诊断结果、当前画像和后续工作流均遵循 Top-18 边界。
- `metrics`、模型元数据、诊断摘要可保留，因为它们不是其余知识点的明细；任何包含逐知识点数组或映射的字段必须投影到同一 18 个 `skill_id`。

## 验收与测试

- 构造 334 项预测及 skill 选择的 18 个 ID，验证标准化结果的 `knowledge_states`、`mastery_rates` 和 `weak_points` 只含这 18 项。
- 验证资源推荐首个 plan 的诊断输入最多 18 项，不会超过模型上下文。
- 验证画像更新会移除前一轮不在 Top-18 的知识点。
- 运行 KT/LPP 适配测试及资源推荐回归测试。
