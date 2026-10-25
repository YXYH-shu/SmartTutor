import test from 'node:test';
import assert from 'node:assert/strict';

import { normalizeDiagnosis, normalizePlan, resolveModuleSnapshot } from '../src/components/agents/learning-modules/moduleData.ts';

test('invalid diagnosis outputs produce an empty view without invented knowledge points', () => {
  for (const output of [null, undefined, [], 'text', 42, true]) {
    assert.deepEqual(normalizeDiagnosis(output), {
      studentId: '', topic: '', summary: '', source: '', points: [], actions: [], weakCount: 0,
    });
  }
});

test('invalid plan outputs produce an empty view without invented stages', () => {
  for (const output of [null, undefined, [], 'text', 42, true]) {
    assert.deepEqual(normalizePlan(output), {
      studentId: '', target: '', targetId: '', estimatedTime: '', rationale: '', stages: [],
    });
  }
});

test('a module with no turn or trace starts pending', () => {
  const result = resolveModuleSnapshot('cognitive_diagnosis', null, null, null, false);
  assert.equal(result?.state, 'pending');
  assert.equal(result?.output, null);
  assert.equal(result?.historical, false);
});

// Compact, unchanged visible fields from the formal-service student 43 capture.
const realDiagnosis = {"kt_student_id":"43","topic_analysis":"学生当前在电学核心概念及安全用电方面基础薄弱，且存在跨学科知识混淆。","diagnosis_summary":"学生在电流、电压、电阻及安全用电等核心电学概念上处于极低掌握水平，同时基础物质分类知识缺失。这表明学生尚未建立电学所需的物理图景，需从最基础的概念定义入手重建认知。","diagnosis_source":"kt","knowledge_states":[{"skill_id":"82","skill_name":"欧姆定律","type":"概念","mastery_percent":"28.4%","mastery_rate":0.2844,"status":"weak","mastery_label":"较低","evidence":"KT 模型预测"},{"skill_id":"114","skill_name":"家用电器安全","type":"概念","mastery_percent":"28.1%","mastery_rate":0.2813,"status":"weak","mastery_label":"较低","evidence":"KT 模型预测"},{"skill_id":"53","skill_name":"安全用电","type":"概念","mastery_percent":"21.6%","mastery_rate":0.2159,"status":"weak","mastery_label":"较低","evidence":"KT 模型预测"},{"skill_id":"201","skill_name":"安全用药","type":"概念","mastery_percent":"20.9%","mastery_rate":0.2089,"status":"weak","mastery_label":"较低","evidence":"KT 模型预测"},{"skill_id":"80","skill_name":"串并联电路","type":"概念","mastery_percent":"21.3%","mastery_rate":0.2133,"status":"weak","mastery_label":"较低","evidence":"KT 模型预测"},{"skill_id":"126","skill_name":"动物分类","type":"概念","mastery_percent":"44.4%","mastery_rate":0.4436,"status":"developing","mastery_label":"中等","evidence":"KT 模型预测"},{"skill_id":"81","skill_name":"电阻与变阻器","type":"概念","mastery_percent":"21.1%","mastery_rate":0.2112,"status":"weak","mastery_label":"较低","evidence":"KT 模型预测"},{"skill_id":"51","skill_name":"电路基本元件","type":"概念","mastery_percent":"23.3%","mastery_rate":0.2328,"status":"weak","mastery_label":"较低","evidence":"KT 模型预测"},{"skill_id":"287","skill_name":"矿产资源利用","type":"概念","mastery_percent":"27.4%","mastery_rate":0.27390000000000003,"status":"weak","mastery_label":"较低","evidence":"KT 模型预测"},{"skill_id":"275","skill_name":"自然资源利用","type":"概念","mastery_percent":"28.3%","mastery_rate":0.2828,"status":"weak","mastery_label":"较低","evidence":"KT 模型预测"},{"skill_id":"112","skill_name":"电流热效应","type":"概念","mastery_percent":"21.6%","mastery_rate":0.21559999999999999,"status":"weak","mastery_label":"较低","evidence":"KT 模型预测"},{"skill_id":"86","skill_name":"电磁感应","type":"概念","mastery_percent":"29.2%","mastery_rate":0.2918,"status":"weak","mastery_label":"较低","evidence":"KT 模型预测"},{"skill_id":"344","skill_name":"模型制作与改进","type":"概念","mastery_percent":"20.3%","mastery_rate":0.2032,"status":"weak","mastery_label":"较低","evidence":"KT 模型预测"},{"skill_id":"258","skill_name":"岩石沙土分类","type":"概念","mastery_percent":"46.0%","mastery_rate":0.46020000000000005,"status":"developing","mastery_label":"中等","evidence":"KT 模型预测"},{"skill_id":"307","skill_name":"淡水资源利用","type":"概念","mastery_percent":"19.3%","mastery_rate":0.19329999999999997,"status":"weak","mastery_label":"极低","evidence":"KT 模型预测"},{"skill_id":"295","skill_name":"海洋资源","type":"概念","mastery_percent":"44.8%","mastery_rate":0.44780000000000003,"status":"developing","mastery_label":"中等","evidence":"KT 模型预测"},{"skill_id":"19","skill_name":"物质性质与分类","type":"概念","mastery_percent":"20.8%","mastery_rate":0.2075,"status":"weak","mastery_label":"较低","evidence":"KT 模型预测"},{"skill_id":"265","skill_name":"自然资源认识","type":"概念","mastery_percent":"20.5%","mastery_rate":0.2046,"status":"weak","mastery_label":"较低","evidence":"KT 模型预测"}],"recommended_actions":["优先复习物质分类与导体/绝缘体概念，为理解电路元件打基础。","通过实物演示或动画视频，直观学习电流、电压、电阻的定义及单位。","结合生活案例（如触电事故）专项学习安全用电常识，强化规则记忆。"]};
const realPlan = {"lpp_student_id":"43","target":{"question_id":774,"question_text":"地壳运动只会引起地震，不会直接影响地表形态。"},"planning_rationale":"本规划严格遵循‘先补前置短板，再构建核心概念，最后迁移应用’的原则。鉴于学生43在‘物质性质与分类’（特别是导体/绝缘体概念）及‘自然/人造资源’认知上存在显著短板（掌握度约20%），且缺乏物理图景，规划将优先利用P1-P2阶段夯实物质基础，通过直观类比（如水流类比）建立电流、电压、电阻的具象认知，而非直接灌输公式。P3阶段将重点构建电路基本元件与连接方式（串联/并联）的逻辑关系，确保学生理解‘电如何流动’。P4-P5阶段则聚焦安全用电与社会责任，将‘安全用电’从单纯的规则记忆转化为对生命安全的敬畏与科学决策能力。整个路径旨在通过低门槛的实物观察与模拟实验，填补认知断层，避免跳跃式学习导致的理解崩塌。","total_estimated_time":"约50分钟","learning_path":[{"stage_id":"P1","name":"P1 · 泌尿系统","objective":"理解并掌握泌尿系统的核心概念与应用。","skills":[{"skill_id":"157","skill_name":"泌尿系统","priority":"必学","estimated_time_min":10,"reason":"这是 LPP Runtime 固定知识点序列中的 P1。"}],"duration_min":10,"checkpoints":["能够解释并应用：泌尿系统"],"resources":[],"expected_outcome":"完成 P1 并能说明泌尿系统的判断依据。"},{"stage_id":"P2","name":"P2 · 动物行为与环境","objective":"理解并掌握动物行为与环境的核心概念与应用。","skills":[{"skill_id":"187","skill_name":"动物行为与环境","priority":"必学","estimated_time_min":10,"reason":"这是 LPP Runtime 固定知识点序列中的 P2。"}],"duration_min":10,"checkpoints":["能够解释并应用：动物行为与环境"],"resources":[],"expected_outcome":"完成 P2 并能说明动物行为与环境的判断依据。"},{"stage_id":"P3","name":"P3 · 空气的质量与空间","objective":"理解并掌握空气的质量与空间的核心概念与应用。","skills":[{"skill_id":"9","skill_name":"空气的质量与空间","priority":"必学","estimated_time_min":10,"reason":"这是 LPP Runtime 固定知识点序列中的 P3。"}],"duration_min":10,"checkpoints":["能够解释并应用：空气的质量与空间"],"resources":[],"expected_outcome":"完成 P3 并能说明空气的质量与空间的判断依据。"},{"stage_id":"P4","name":"P4 · 粒子模型与三态","objective":"理解并掌握粒子模型与三态的核心概念与应用。","skills":[{"skill_id":"29","skill_name":"粒子模型与三态","priority":"必学","estimated_time_min":10,"reason":"这是 LPP Runtime 固定知识点序列中的 P4。"}],"duration_min":10,"checkpoints":["能够解释并应用：粒子模型与三态"],"resources":[],"expected_outcome":"完成 P4 并能说明粒子模型与三态的判断依据。"},{"stage_id":"P5","name":"P5 · 发明方法与原理","objective":"理解并掌握发明方法与原理的核心概念与应用。","skills":[{"skill_id":"322","skill_name":"发明方法与原理","priority":"必学","estimated_time_min":10,"reason":"这是 LPP Runtime 固定知识点序列中的 P5。"}],"duration_min":10,"checkpoints":["能够解释并应用：发明方法与原理"],"resources":[],"expected_outcome":"完成 P5 并能说明发明方法与原理的判断依据。"}],"recommended_knowledge_points":[{"order":1,"knowledge_point_id":157,"knowledge_point_name":"泌尿系统"},{"order":2,"knowledge_point_id":187,"knowledge_point_name":"动物行为与环境"},{"order":3,"knowledge_point_id":9,"knowledge_point_name":"空气的质量与空间"},{"order":4,"knowledge_point_id":29,"knowledge_point_name":"粒子模型与三态"},{"order":5,"knowledge_point_id":322,"knowledge_point_name":"发明方法与原理"}]};

const turn = (items = [], extra = {}) => ({
  turnId: 'current', startedAt: 2000, agentTimeline: items,
  touchedNodes: [], focusAgents: [], ...extra,
});
const item = (status, output, extra = {}) => ({
  agentName: 'cognitive_diagnosis', status, output, startedAt: 2100, durationMs: 123, ...extra,
});
const trace = (output, updatedAt = 1500) => ({
  content: typeof output === 'string' ? output : JSON.stringify(output),
  label: '诊断', updatedAt: new Date(updatedAt).toISOString(),
});

test('real diagnosis keeps all 18 points, full names, mastery and teaching advice', () => {
  const data = normalizeDiagnosis(realDiagnosis);
  assert.equal(data.studentId, '43');
  assert.equal(data.topic, realDiagnosis.topic_analysis);
  assert.equal(data.summary, realDiagnosis.diagnosis_summary);
  assert.equal(data.source, 'KT');
  assert.equal(data.points.length, 18);
  assert.deepEqual(data.points.map((p) => p.id), [
    '82', '114', '53', '201', '80', '126', '81', '51', '287', '275', '112', '86', '344', '258', '307', '295', '19', '265',
  ]);
  assert.deepEqual(data.points[0], { id: '82', name: '欧姆定律', mastery: 0.2844, status: 'weak', evidence: 'KT 模型预测' });
  assert.equal(data.points[12].name, '模型制作与改进');
  assert.equal(data.weakCount, 15);
  assert.deepEqual(data.actions, realDiagnosis.recommended_actions);
});

test('zero and threshold mastery are preserved while invalid values stay unknown', () => {
  const values = [0, 0.3999, 0.4, 0.6999, 0.7, 1, null, undefined, -1, 1.1, NaN, Infinity, '', '0.7', false];
  const output = { knowledge_states: values.map((mastery_rate, i) => ({ skill_id: i, skill_name: `完整知识点名称${i}`, mastery_rate, status: 'mastered' })) };
  const data = normalizeDiagnosis(output);
  assert.deepEqual(data.points.map((p) => p.mastery), [0, 0.3999, 0.4, 0.6999, 0.7, 1, null, null, null, null, null, null, null, null, null]);
  assert.deepEqual(data.points.map((p) => p.status), ['weak', 'weak', 'developing', 'developing', 'mastered', 'mastered', ...Array(9).fill('unknown')]);
  assert.equal(data.points[0].id, '0');
  assert.equal(data.points[14].name, '完整知识点名称14');
  assert.equal(data.weakCount, 2);
});

test('diagnosis preserves supplied order and can read graph names and a mastery map', () => {
  const data = normalizeDiagnosis({
    knowledge_graph: { nodes: [{ id: 'b', label: '完整的第二知识点名称' }, { id: 'a', name: '第一知识点' }] },
    mastery_rates: { a: 0.8, b: 0 },
  });
  assert.deepEqual(data.points, [
    { id: 'b', name: '完整的第二知识点名称', mastery: 0, status: 'weak', evidence: '' },
    { id: 'a', name: '第一知识点', mastery: 0.8, status: 'mastered', evidence: '' },
  ]);
});

test('malformed entries and actions do not become invented text', () => {
  const data = normalizeDiagnosis({ knowledge_states: [null, 42, {}, { skill_name: '已提供名称' }], recommended_actions: ['保留建议', 123, null, {}, ''] });
  assert.deepEqual(data.points, [
    { id: '', name: '', mastery: null, status: 'unknown', evidence: '' },
    { id: '', name: '已提供名称', mastery: null, status: 'unknown', evidence: '' },
  ]);
  assert.deepEqual(data.actions, ['保留建议']);
});

test('real plan keeps exact P1-P5 names and their objectives, reasons and checkpoints', () => {
  const data = normalizePlan(realPlan);
  assert.equal(data.studentId, '43');
  assert.equal(data.targetId, '774');
  assert.equal(data.target, '地壳运动只会引起地震，不会直接影响地表形态。');
  assert.equal(data.estimatedTime, '约50分钟');
  assert.equal(data.rationale, realPlan.planning_rationale);
  assert.deepEqual(data.stages.map((s) => s.name), ['P1 · 泌尿系统', 'P2 · 动物行为与环境', 'P3 · 空气的质量与空间', 'P4 · 粒子模型与三态', 'P5 · 发明方法与原理']);
  assert.deepEqual(data.stages[0], {
    id: 'P1', name: 'P1 · 泌尿系统', objective: '理解并掌握泌尿系统的核心概念与应用。',
    reason: '这是 LPP Runtime 固定知识点序列中的 P1。', checkpoints: ['能够解释并应用：泌尿系统'],
    outcome: '完成 P1 并能说明泌尿系统的判断依据。', duration: '10分钟',
  });
});

test('plan never sorts stages or replaces supplied names with position-based names', () => {
  const data = normalizePlan({ learning_path: [realPlan.learning_path[3], realPlan.learning_path[0], realPlan.learning_path[2]], stages: realPlan.learning_path });
  assert.deepEqual(data.stages.map((s) => s.id), ['P4', 'P1', 'P3']);
  assert.equal(data.stages[0].name, 'P4 · 粒子模型与三态');
});

test('stages are used when learning_path is missing or empty', () => {
  for (const learning_path of [undefined, []]) {
    const data = normalizePlan({ learning_path, stages: [{ stage_id: 'P5', name: '真实阶段', objective: '真实目标', reason: '真实原因', duration_min: 0, checkpoints: ['检查', null], expected_outcome: '成果' }] });
    assert.deepEqual(data.stages, [{ id: 'P5', name: '真实阶段', objective: '真实目标', reason: '真实原因', duration: '0分钟', checkpoints: ['检查'], outcome: '成果' }]);
  }
});

test('recommended points are an ordered fallback with no invented objectives', () => {
  const data = normalizePlan({ recommended_knowledge_points: [
    { order: 5, knowledge_point_id: 322, knowledge_point_name: '发明方法与原理' },
    { order: 1, knowledge_point_id: 157, knowledge_point_name: '泌尿系统' },
  ] });
  assert.deepEqual(data.stages, [
    { id: 'P5', name: '发明方法与原理', objective: '', reason: '', checkpoints: [], outcome: '', duration: '' },
    { id: 'P1', name: '泌尿系统', objective: '', reason: '', checkpoints: [], outcome: '', duration: '' },
  ]);
});

test('missing stage fields remain empty and malformed values do not leak into text', () => {
  const data = normalizePlan({ target: { question_id: 0, question_text: {} }, learning_path: [null, false, {}, { name: '实际名称', objective: {}, reason: [], duration_min: -1 }] });
  assert.equal(data.targetId, '0');
  assert.equal(data.target, '');
  assert.deepEqual(data.stages, [
    { id: '', name: '', objective: '', reason: '', checkpoints: [], outcome: '', duration: '' },
    { id: '', name: '实际名称', objective: '', reason: '', checkpoints: [], outcome: '', duration: '' },
  ]);
});

test('matching timeline output is preferred over any newer trace', () => {
  const result = resolveModuleSnapshot('cognitive_diagnosis', trace({ knowledge_states: [{ skill_name: '错误的旧数据' }] }, 3000), turn([item('completed', realDiagnosis)]), null, false);
  assert.equal(result.state, 'completed');
  assert.equal(result.output, realDiagnosis);
  assert.equal(result.durationMs, 123);
  assert.equal(result.historical, false);
});

test('JSON timeline output is parsed while timeout or failure overrides completed', () => {
  for (const [output, state] of [[{ status: 'timeout', continued: true }, 'timeout'], [{ status: 'failed', continued: true }, 'error'], [{ error: 'model unavailable' }, 'error']]) {
    const result = resolveModuleSnapshot('cognitive_diagnosis', trace(realDiagnosis), turn([item('completed', JSON.stringify(output))]), null, false);
    assert.equal(result.state, state);
    assert.deepEqual(result.output, output);
    assert.equal(result.historical, false);
    assert.ok(result.message.length > 0);
  }
});

test('a new running node hides its stale output and the previous turn trace', () => {
  const result = resolveModuleSnapshot('cognitive_diagnosis', trace(realDiagnosis), turn([item('running', realDiagnosis)]), 'cognitive_diagnosis', true);
  assert.equal(result.state, 'running');
  assert.equal(result.output, null);
  assert.equal(result.historical, false);
});

test('stopping execution changes a running node to interrupted and hides unfinished output', () => {
  const result = resolveModuleSnapshot('cognitive_diagnosis', trace(realDiagnosis), turn([item('running', realDiagnosis)]), null, false);
  assert.equal(result.state, 'interrupted');
  assert.equal(result.output, null);
  assert.equal(result.historical, false);
});

test('an executing new turn cannot show an unrelated historical module result', () => {
  const result = resolveModuleSnapshot('cognitive_diagnosis', trace(realDiagnosis), turn([item('running', null, { agentName: 'learning_path' })]), 'learning_path', true);
  assert.equal(result.state, 'pending');
  assert.equal(result.output, null);
  assert.equal(result.historical, false);
});

test('only a completed matching node can use a trace known to belong to this turn', () => {
  const old = resolveModuleSnapshot('cognitive_diagnosis', trace(realDiagnosis), turn([item('completed', undefined)]), null, false);
  assert.equal(old.state, 'incomplete');
  assert.equal(old.output, null);
  const fresh = resolveModuleSnapshot('cognitive_diagnosis', trace(realDiagnosis, 2200), turn([item('completed', undefined)]), null, false);
  assert.equal(fresh.state, 'completed');
  assert.deepEqual(fresh.output, realDiagnosis);
  assert.equal(fresh.historical, false);
});

test('idle trace-only data is explicitly historical', () => {
  for (const currentTurn of [null, turn([], { endedAt: 2400 })]) {
    const result = resolveModuleSnapshot('cognitive_diagnosis', trace(realDiagnosis), currentTurn, null, false);
    assert.equal(result.state, 'completed');
    assert.deepEqual(result.output, realDiagnosis);
    assert.equal(result.historical, true);
  }
});

test('a current agent without a timeline is running and never reads old trace', () => {
  const result = resolveModuleSnapshot('cognitive_diagnosis', trace(realDiagnosis), turn(), 'cognitive_diagnosis', true);
  assert.equal(result.state, 'running');
  assert.equal(result.output, null);
});

test('pending nodes, failed nodes, and malformed completion stay distinct', () => {
  const pending = resolveModuleSnapshot('cognitive_diagnosis', trace(realDiagnosis), turn([item('pending', undefined)]), null, true);
  assert.equal(pending.state, 'pending');
  assert.equal(pending.output, null);
  const failed = resolveModuleSnapshot('cognitive_diagnosis', trace(realDiagnosis), turn([item('error', undefined)]), null, false);
  assert.equal(failed.state, 'error');
  assert.equal(failed.output, null);
  for (const output of ['not json', 'null', '[]', '{}', 42, null]) {
    const result = resolveModuleSnapshot('cognitive_diagnosis', trace(realDiagnosis), turn([item('completed', output)]), null, false);
    assert.equal(result.state, 'incomplete');
    assert.equal(result.historical, false);
  }
});

test('the latest matching timeline attempt wins without mutating inputs', () => {
  const input = turn([item('completed', realDiagnosis), item('running', undefined, { startedAt: 2300 })]);
  const before = JSON.stringify(input);
  assert.equal(resolveModuleSnapshot('cognitive_diagnosis', trace(realDiagnosis), input, 'cognitive_diagnosis', true).state, 'running');
  normalizeDiagnosis(realDiagnosis);
  normalizePlan(realPlan);
  assert.equal(JSON.stringify(input), before);
});

test('learning path snapshots recognize real stages and unavailable responses', () => {
  const completed = resolveModuleSnapshot('learning_path', null, turn([item('completed', JSON.stringify(realPlan), { agentName: 'learning_path' })]), 'learning_path', true);
  assert.equal(completed.state, 'completed');
  const unavailable = resolveModuleSnapshot('learning_path', null, turn([item('completed', { lpp_source: 'lpp_unavailable', learning_path: [] }, { agentName: 'learning_path' })]), null, false);
  assert.equal(unavailable.state, 'error');
});

test('planning completion requires exactly five named stages for current and historical data', () => {
  const cases = [
    { stages: realPlan.learning_path.slice(0, 1), state: 'incomplete' },
    { stages: realPlan.learning_path.slice(0, 4), state: 'incomplete' },
    { stages: realPlan.learning_path, state: 'completed' },
    { stages: [...realPlan.learning_path, realPlan.learning_path[0]], state: 'incomplete' },
    { stages: [...realPlan.learning_path.slice(0, 4), { stage_id: 'P5', name: '   ' }], state: 'incomplete' },
    { stages: [...realPlan.learning_path.slice(0, 4), { stage_id: 'P5' }], state: 'incomplete' },
  ];
  for (const { stages, state } of cases) {
    const output = { learning_path: stages };
    const current = resolveModuleSnapshot('learning_path', null, turn([item('completed', output, { agentName: 'learning_path' })]), null, false);
    const historical = resolveModuleSnapshot('learning_path', trace(output), null, null, false);
    assert.equal(current.state, state, `current ${stages.length} stages`);
    assert.equal(historical.state, state, `historical ${stages.length} stages`);
    assert.equal(historical.historical, true);
    assert.equal(normalizePlan(output).stages.length, stages.length);
  }
});

test('unavailable planning sources are errors even when five fallback points exist', () => {
  for (const lpp_source of ['unavailable', 'lpp_unavailable']) {
    const output = { lpp_source, recommended_knowledge_points: realPlan.recommended_knowledge_points };
    const current = resolveModuleSnapshot('learning_path', null, turn([item('completed', output, { agentName: 'learning_path' })]), null, false);
    const historical = resolveModuleSnapshot('learning_path', trace(output), null, null, false);
    assert.equal(current.state, 'error');
    assert.equal(historical.state, 'error');
    assert.equal(current.output, output);
  }
});

test('running duration uses elapsed time and interruption retains only recorded duration', (t) => {
  t.mock.method(Date, 'now', () => 5000);
  const current = turn([item('running', undefined)]);
  assert.equal(resolveModuleSnapshot('cognitive_diagnosis', null, current, 'cognitive_diagnosis', true).durationMs, 2900);
  assert.equal(resolveModuleSnapshot('cognitive_diagnosis', null, current, null, false).durationMs, 123);
  const unrecorded = turn([item('running', undefined, { durationMs: undefined })]);
  assert.equal(resolveModuleSnapshot('cognitive_diagnosis', null, unrecorded, null, false).durationMs, undefined);
  for (const startedAt of [undefined, NaN, Infinity, -1, 6000]) {
    const invalid = turn([item('running', undefined, { startedAt, durationMs: undefined })]);
    assert.equal(resolveModuleSnapshot('cognitive_diagnosis', null, invalid, 'cognitive_diagnosis', true).durationMs, undefined);
  }
});

test('diagnosis source case is displayed without inventing missing provenance', () => {
  assert.equal(normalizeDiagnosis({ diagnosis_source: 'kt' }).source, 'KT');
  assert.equal(normalizeDiagnosis({ diagnosis_source: 'KT' }).source, 'KT');
  assert.equal(normalizeDiagnosis({ diagnosis_source: 'llm' }).source, 'llm');
  assert.equal(normalizeDiagnosis({}).source, '');
});

test('fallback stage labels use supplied stage ids or order and never knowledge point ids', () => {
  const data = normalizePlan({ recommended_knowledge_points: [
    { stage_id: 'P4', order: 1, knowledge_point_id: 157, knowledge_point_name: '真实一' },
    { order: 3, knowledge_point_id: 322, knowledge_point_name: '真实二' },
    { knowledge_point_id: 9, knowledge_point_name: '真实三' },
  ] });
  assert.deepEqual(data.stages.map((stage) => stage.id), ['P4', 'P3', 'P3']);
  assert.deepEqual(data.stages.map((stage) => stage.name), ['真实一', '真实二', '真实三']);
});

test('diagnosis retains semantic rank, extension label and reason without reordering by mastery', () => {
  const data = normalizeDiagnosis({knowledge_states: [
    {skill_id: '82', skill_name: '欧姆定律', mastery_rate: 0.8, relevance_rank: 1, relevance_tier: 'related', relevance_reason: '直接解释电流电压电阻关系'},
    {skill_id: '253', skill_name: '太阳系组成', mastery_rate: 0.1, relevance_rank: 18, relevance_tier: 'extended', relevance_reason: '弱关联的拓展诊断'},
  ]});
  assert.deepEqual(data.points.map(p => p.id), ['82', '253']);
  assert.equal(data.points[0].relevanceRank, 1);
  assert.equal(data.points[1].relevanceTier, 'extended');
  assert.equal(data.points[1].relevanceReason, '弱关联的拓展诊断');
});
