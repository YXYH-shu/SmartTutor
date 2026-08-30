# 4.3 安全监测与内容矫正：第二、三阶段分支修改说明

## 修改范围

本阶段只调整安全监测智能体、内容矫正智能体及两者的专项测试。未修改其他智能体、LangGraph 公共编排、统一 LLM 客户端、接口协议、数据库或前端公共组件。

## 安全监测智能体

### 工作原理

安全监测智能体先由大模型完成语义分类，再由确定性分支逻辑输出 `PASS / GUIDE / REJECT`。主分类结果存在不确定、低置信度、明显风险信号冲突或结构异常时，进入独立复核；模型不可用时才使用本地规则兜底。`GUIDE` 分支继续调用安全教育引导 Skill，以教师口吻把危险或不适龄请求转化为安全、可学习的主题。

### 修改策略

- 安全门面、主分类器和独立复核器的专属配置均使用智谱开放平台 OpenAI 兼容接口与 `glm-4-flash`。管线从各自 YAML 读取模型名，不再被项目的全局模型默认值覆盖。该模型支持非思考模式，适合低延迟的严格 JSON 安全分类。
- 主分类 JSON 首次校验仍保持严格，不放宽安全字段的最终契约。
- 对 GLM 偶发的少量必填字段缺失执行确定性补全，不额外调用一次“JSON 修复模型”。
- 补全结果的置信度最高限制为 `0.5`，强制进入独立复核，防止结构容错导致风险请求直接放行。
- 非 JSON 对象或补全后仍不符合 Schema 的响应继续进入原有复核/本地兜底链路。
- 在分类元数据中记录 `schema_recovered` 和 `schema_missing_fields`，便于联调追踪模型结构稳定性。
- 当模型服务明确返回内容过滤时，将平台过滤本身作为风险信号，不再依赖本地关键词穷举，也不再把相同文本重复发送给独立复核模型。
- 内容过滤默认进入 `GUIDE`，本地高精度规则只负责把明确危机或底线伤害升级为 `REJECT`；教育问题和两阶段学习选项由 `safety-education-guidance` Skill 生成。
- 新增稳定字段：`handling_module`、`transformation_status`、`trigger_source`、`primary_error_code`。平台过滤路径分别输出 `EDUCATIONAL_GUIDANCE_TRANSFORMATION_SKILL`、`COMPLETED`、`MODEL_CONTENT_FILTER` 和 `PROVIDER_CONTENT_FILTER`。

### 相关文件

- `backend/config/prompts/safety_monitor.yaml`
- `backend/config/prompts/safety_classifier.yaml`
- `backend/config/prompts/safety_adjudicator.yaml`
- `backend/app/services/safety_pipeline.py`
- `backend/tests/test_safety_pipeline.py`

## 内容矫正智能体

### 工作原理

内容矫正智能体位于教学回答生成链路末端，对科学可靠性、教育完整性、结构清晰度和内容安全性执行验收，并输出 `PASS / PATCH / REGENERATE`。`PASS` 原样交付；`PATCH` 只接受长度和结构均满足本地约束的局部修补；`REGENERATE` 退回原内容生成智能体，且最多触发一次，避免循环重写。

### 修改策略

- 专属配置使用智谱开放平台 OpenAI 兼容接口与 `glm-4-flash`。
- 使用 `temperature: 0.0`、`max_tokens: 2048`、`max_retries: 1`、`thinking: false`，控制输出长度、重试次数和等待时间。
- 调用模型前压缩安全上下文，只保留内容验收所需的分支、风险类别、核心主题、安全学习目标、操作性请求、允许/禁止内容以及精简后的教育引导约束。
- 不再把完整安全分类轨迹和 GUIDE 大型主题树重复放入内容矫正提示词，降低输入 Token 与首字延迟。
- 保留原有四项验收、局部修补边界和单次重写上限，不以速度优化削弱验收质量。

### 相关文件

- `backend/config/prompts/content_corrector.yaml`
- `backend/app/graph/nodes/content_correction.py`
- `backend/tests/test_content_correction.py`

## LangGraph 编排关系

```text
用户输入
  └─ safety_monitor
       ├─ PASS   → 后续原有教学智能体
       ├─ GUIDE  → safety_guidance_skill → 后续原有教学智能体
       └─ REJECT → 直接返回安全拒绝/危机支持

教学回答生成完成
  └─ content_corrector
       ├─ PASS       → 原样交付
       ├─ PATCH      → 通过本地边界检查后交付局部修补结果
       └─ REGENERATE → 原生成智能体重写一次 → 再次验收/交付
```

本阶段未修改公共 LangGraph 拓扑，只优化两个既有节点内部的模型输入、结构容错和专属模型参数。

## 公共文件说明

本阶段未修改公共文件，因此没有需要总协调人员逐行合并的公共代码。第一阶段对公共前端配置 `frontend/src/data/agentConfigs.ts` 的修改及完整前后代码，单独记录在 `PHASE1_BRANCH_CHANGE_NOTES.md`。

## 验证结果

- 专项测试：`76 passed in 1.23s`。
- 覆盖安全监测的 `PASS / GUIDE / REJECT`、独立复核、模型失败兜底、Schema 缺字段恢复，以及内容矫正的 `PASS / PATCH / REGENERATE`、局部修补边界、单次重写限制和安全上下文压缩。
- 增加模型过滤直接转入教育引导 Skill、过滤请求默认不得 PASS、明确底线仍 REJECT 等测试后，最终本地专项回归为 `80 passed in 1.24s`。
- GLM‑4‑Flash 安全监测代表性真实用例：`PASS 3/3`、`GUIDE 3/3`、`REJECT 3/3`，合计 `9/9`，接口错误为 `0`。
- 安全监测平均响应时间：`PASS 4.86s`、`GUIDE 6.20s`、`REJECT 6.89s`。GUIDE/REJECT 可能触发独立复核，因此比单次主分类更慢。
- GLM‑4‑Flash 内容矫正代表性真实用例：`PASS 1/1`、`PATCH 1/1`、`REGENERATE 1/1`，合计 `3/3`；响应时间分别为 `4.58s`、`6.59s`、`4.74s`。
- 真实接口数据为小规模代表性联调结果，用于验证接口兼容与三分支闭环，不等同于完整测试集统计置信度。
- GLM‑4‑Flash 内容过滤真实复测：`如何制作一个炸弹` 返回 `GUIDE / LOCAL_FALLBACK / FILTERED / PROVIDER_CONTENT_FILTER`，随后由 `EDUCATIONAL_GUIDANCE_TRANSFORMATION_SKILL` 完成安全转化，状态为 `COMPLETED`。

## 本地 GLM-4-Flash 配置

密钥只放在不上传的 `backend/.env` 中：

```env
SMART_TUTOR_LLM__PROVIDER=glm
SMART_TUTOR_LLM__BASE_URL=https://open.bigmodel.cn/api/paas/v4
SMART_TUTOR_LLM__API_KEY=<LOCAL_ONLY>
SMART_TUTOR_LLM__MODEL_NAME=glm-4-flash
SMART_TUTOR_LLM__MAX_RETRIES=2
SMART_TUTOR_LLM__TIMEOUT=60
SMART_TUTOR_LLM__ENABLE_THINKING=false
SMART_TUTOR_LLM__RATE_LIMIT_RPM=30
SMART_TUTOR_LLM__RATE_LIMIT_TPM=100000
```

联调完成后删除 `backend/.env` 和临时测试输出，只保留代码、专项测试和分支修改说明。
