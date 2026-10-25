from __future__ import annotations

import copy
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import settings
from app.services.agents.cognitive_diagnosis import CognitiveDiagnosisAgent
from app.services.agents.learning_path import LearningPathAgent
from app.services.lpp_integration import LppRuntimeOutput

NAMES = {8: '材料透光与导电性', 51: '电路基本元件', 53: '安全用电', 81: '电阻与变阻器', 82: '欧姆定律', 193: '生物多样性保护'}


def retrieval(turn='turn-current'):
    return {
        'status': 'ok', 'method': 'llm_closed_catalog', 'source_turn_id': turn,
        'message': '相关主题',
        'topic_context': {'current_query': '动物皮肤导电性', 'selected_option': '电阻与动物保护', 'original_query': '风险原句', 'safe_query': '动物皮肤导电性'},
        'queries': {'core': ['导电性与电阻'], 'prerequisite': ['材料的导电性'], 'safety_ethics': ['保护动物与安全用电'], 'application': []},
        'matches': [{'skill_id': sid, 'skill_name': name, 'role': 'safety_ethics' if sid in (53, 193) else 'prerequisite' if sid == 8 else 'core', 'reason': f'{name}用于解释动物皮肤导电性和保护边界'} for sid, name in NAMES.items()],
    }


def kt_result():
    states = [{'skill_id': str(sid), 'skill_name': name, 'mastery_rate': .27, 'mastery_percent': '27.0%', 'status': 'weak', 'type': '概念'} for sid, name in reversed(NAMES.items())]
    states.append({'skill_id': '253', 'skill_name': '太阳系组成', 'mastery_rate': .1, 'status': 'weak'})
    return {'knowledge_states': states, 'mastery_rates': {x['skill_id']: x['mastery_rate'] for x in states}, 'weak_points': states, 'metrics': {}, 'model_info': {}}


def llm_agent(cls):
    llm = MagicMock()
    llm.chat_completion = AsyncMock(return_value={'content': {'topic_analysis': '动物皮肤导电性', 'cognitive_attribution': {'root_causes': []}, 'diagnosis_summary': '巩固导电性', 'recommended_actions': ['学习电阻'], 'planning_rationale': '保护动物并学习电学', 'adaptive_rules': '按检查点复习'}, 'usage': {}})
    llm.validate_json_response = AsyncMock(side_effect=lambda content, schema: content)
    agent = cls(llm=llm)
    agent._log_execution = AsyncMock()
    agent.post_process = AsyncMock()
    return agent


def runtime_result(ids=(193, 53, 8, 81, 82)):
    points = [{'order': i + 1, 'knowledge_point_id': sid, 'knowledge_point_name': NAMES.get(sid, '太阳系组成')} for i, sid in enumerate(ids)]
    return {'status': 'ok', 'message': 'recommendations_ready', 'student_id': '43', 'target': {'question_id': 500, 'question_text': '材料的导电性与电阻', 'knowledge_points': [{'knowledge_point_id': 81, 'knowledge_point_name': NAMES[81]}]}, 'recommendation': {'count': 5, 'knowledge_points': points, 'questions': []}, 'diagnostics': {}}


@pytest.mark.asyncio
async def test_diagnosis_semantic_selection_constrains_kt_and_records_relevance(monkeypatch):
    selected = retrieval()
    retrieve = AsyncMock(return_value=selected)
    monkeypatch.setattr('app.services.agents.cognitive_diagnosis.retrieve_topic_knowledge', retrieve, raising=False)
    monkeypatch.setattr(settings.kt, 'mode', 'integrated')
    agent = llm_agent(CognitiveDiagnosisAgent)
    agent._run_kt_diagnosis = AsyncMock(return_value=kt_result())
    result = await agent.execute({'current_message': '动物皮肤导电性', 'recent_messages': []}, {'turn_id': 'turn-current'})
    retrieve.assert_awaited_once()
    passed = agent._run_kt_diagnosis.await_args.args[1]
    assert set(str(passed.get('targets', '')).split(',')) == {str(x) for x in NAMES}
    assert '保护动物' in passed.get('history_context', '')
    assert 'original_query' not in result['output'].get('topic_context', {}) or result['output']['topic_context']['original_query'] == '风险原句'
    output = result['output']
    assert [x['skill_id'] for x in output['knowledge_states']] == [str(x) for x in NAMES]
    assert set(output['mastery_rates']) == {str(x) for x in NAMES}
    assert all(x['skill_id'] != '253' for x in output['weak_points'])
    assert output['knowledge_retrieval']['method'] == 'llm_closed_catalog'
    assert output['knowledge_retrieval']['source_turn_id'] == 'turn-current'
    assert output['knowledge_states'][0]['mastery_rate'] == .27
    assert NAMES[8] in output['knowledge_states'][0]['relevance_reason']
    rendered = agent.llm.chat_completion.await_args.kwargs['prompt']
    assert '风险原句' not in rendered
    assert json.dumps('风险原句', ensure_ascii=True)[1:-1] not in rendered
    assert '保护动物' in rendered or json.dumps('保护动物', ensure_ascii=True)[1:-1] in rendered


@pytest.mark.asyncio
@pytest.mark.parametrize('status', ['no_match', 'unavailable'])
async def test_diagnosis_does_not_fall_back_to_unrelated_kt_when_topic_retrieval_fails(monkeypatch, status):
    failed = {**retrieval(), 'status': status, 'matches': [], 'message': '未找到相关知识点'}
    retrieve = AsyncMock(return_value=failed)
    monkeypatch.setattr('app.services.agents.cognitive_diagnosis.retrieve_topic_knowledge', retrieve, raising=False)
    monkeypatch.setattr(settings.kt, 'mode', 'integrated')
    agent = llm_agent(CognitiveDiagnosisAgent)
    agent._run_kt_diagnosis = AsyncMock(return_value=kt_result())
    result = await agent.execute({'current_message': '目录不覆盖的主题'}, {})
    agent._run_kt_diagnosis.assert_not_awaited()
    agent.llm.chat_completion.assert_not_awaited()
    assert result['output']['knowledge_states'] == []
    assert result['output']['knowledge_retrieval']['status'] == status


@pytest.mark.asyncio
async def test_planning_reuses_this_turn_selection_and_constrains_runtime(monkeypatch):
    retrieve = AsyncMock(return_value=retrieval())
    monkeypatch.setattr('app.services.agents.learning_path.retrieve_topic_knowledge', retrieve, raising=False)
    runtime = runtime_result()
    run = AsyncMock(return_value=LppRuntimeOutput(data=runtime, raw_json='{}'))
    monkeypatch.setattr('app.services.agents.learning_path.run_lpp_for_student', run)
    monkeypatch.setattr(settings.lpp, 'enabled', True)
    agent = llm_agent(LearningPathAgent)
    diagnosis = kt_result()
    diagnosis['knowledge_retrieval'] = retrieval()
    result = await agent.execute({'current_message': '动物皮肤导电性', 'diagnosis_result': diagnosis}, {'turn_id': 'turn-current'})
    retrieve.assert_not_awaited()
    assert set(run.await_args.kwargs.get('topic_skill_ids', [])) == set(NAMES)
    assert set(run.await_args.kwargs.get('preferred_skill_ids', [])) <= set(NAMES)
    stages = result['output']['learning_path']
    assert {int(x['skills'][0]['skill_id']) for x in stages} <= set(NAMES)
    assert '动物' in stages[0]['skills'][0]['reason']
    assert result['output']['knowledge_retrieval']['status'] == 'ok'


@pytest.mark.asyncio
async def test_planning_does_not_reuse_other_turn_stale_topic(monkeypatch):
    fresh = retrieval('new-turn')
    retrieve = AsyncMock(return_value=fresh)
    monkeypatch.setattr('app.services.agents.learning_path.retrieve_topic_knowledge', retrieve, raising=False)
    run = AsyncMock(return_value=LppRuntimeOutput(data=runtime_result(), raw_json='{}'))
    monkeypatch.setattr('app.services.agents.learning_path.run_lpp_for_student', run)
    agent = llm_agent(LearningPathAgent)
    stale = {'diagnosis_summary': '太阳系的历史诊断', 'knowledge_states': [{'skill_id': '253', 'mastery_rate': .1}], 'knowledge_retrieval': {**retrieval('old-turn'), 'topic_context': {'current_query': '太阳系组成'}}}
    await agent.execute({'current_message': '动物皮肤导电性', 'diagnosis_result': stale}, {'turn_id': 'new-turn'})
    retrieve.assert_awaited_once()
    assert 253 not in run.await_args.kwargs.get('topic_skill_ids', [])
    rendered = agent.llm.chat_completion.await_args.kwargs['prompt']
    assert '太阳系的历史诊断' not in rendered


@pytest.mark.asyncio
async def test_planning_rejects_runtime_stage_outside_semantic_topic(monkeypatch):
    monkeypatch.setattr('app.services.agents.learning_path.retrieve_topic_knowledge', AsyncMock(return_value=retrieval()), raising=False)
    run = AsyncMock(return_value=LppRuntimeOutput(data=runtime_result((193, 53, 8, 81, 253)), raw_json='{}'))
    monkeypatch.setattr('app.services.agents.learning_path.run_lpp_for_student', run)
    agent = llm_agent(LearningPathAgent)
    result = await agent.execute({'current_message': '动物皮肤导电性'}, {'turn_id': 'turn-current'})
    assert result['output']['lpp_source'] == 'lpp_unavailable'
    assert result['output']['learning_path'] == []
    agent.llm.chat_completion.assert_not_awaited()


@pytest.mark.asyncio
async def test_planning_refreshes_even_identical_topic_from_a_previous_turn(monkeypatch):
    from app.services.topic_retrieval import build_topic_context
    data = {'current_message': '动物皮肤导电性'}
    old = retrieval('old-turn')
    old['topic_context'] = build_topic_context(data)
    data['diagnosis_result'] = {'knowledge_retrieval': old, 'diagnosis_summary': 'OLD_DIAGNOSIS'}
    retrieve = AsyncMock(return_value=retrieval('new-turn'))
    monkeypatch.setattr('app.services.agents.learning_path.retrieve_topic_knowledge', retrieve)
    monkeypatch.setattr('app.services.agents.learning_path.run_lpp_for_student', AsyncMock(return_value=LppRuntimeOutput(data=runtime_result(), raw_json='{}')))
    agent = llm_agent(LearningPathAgent)
    await agent.execute(data, {'turn_id': 'new-turn'})
    retrieve.assert_awaited_once()
    assert 'OLD_DIAGNOSIS' not in agent.llm.chat_completion.await_args.kwargs['prompt']


@pytest.mark.asyncio
@pytest.mark.parametrize('agent_class,module', [(CognitiveDiagnosisAgent, 'cognitive_diagnosis'), (LearningPathAgent, 'learning_path')])
async def test_transformed_agent_explanation_never_uses_risky_current_history_or_goal(monkeypatch, agent_class, module):
    selected = retrieval()
    selected['topic_context']['safety_transformed'] = True
    selected['topic_context']['original_query'] = '风险原句'
    monkeypatch.setattr(f'app.services.agents.{module}.retrieve_topic_knowledge', AsyncMock(return_value=selected))
    monkeypatch.setattr('app.services.agents.learning_path.run_lpp_for_student', AsyncMock(return_value=LppRuntimeOutput(data=runtime_result(), raw_json='{}')))
    agent = llm_agent(agent_class)
    agent._run_kt_diagnosis = AsyncMock(return_value=kt_result())
    await agent.execute({'current_message': '风险原句', 'recent_messages': [{'role': 'human', 'content': '风险原句'}], 'message_history': [{'role': 'human', 'content': '风险原句'}], 'goal': '风险原句'}, {'turn_id': 'turn-current'})
    rendered = agent.llm.chat_completion.await_args.kwargs['prompt']
    assert '风险原句' not in rendered
    assert json.dumps('风险原句', ensure_ascii=True)[1:-1] not in rendered
    assert '动物皮肤导电性' in rendered


def test_followup_explanation_uses_fresh_safe_core_queries_and_omits_old_raw_history():
    from app.services.topic_retrieval import prepare_topic_explanation_input
    selected = retrieval()
    selected['topic_context']['previous_learning_topic'] = {'safe_query': '动物皮肤导电性', 'selected_option': '动物保护'}
    prepared = prepare_topic_explanation_input({'current_message': '按上面的主题给我路径', 'recent_messages': [{'role': 'human', 'content': '风险原句'}], 'goal': '按上面'}, selected)
    assert '风险原句' not in json.dumps(prepared['recent_messages'], ensure_ascii=False)
    assert '导电性与电阻' in prepared['current_message']


@pytest.mark.asyncio
async def test_planning_rationale_uses_actual_stages_and_relevance_instead_of_llm_reordering(monkeypatch):
    selected = retrieval()
    monkeypatch.setattr('app.services.agents.learning_path.retrieve_topic_knowledge', AsyncMock(return_value=selected))
    monkeypatch.setattr('app.services.agents.learning_path.run_lpp_for_student', AsyncMock(return_value=LppRuntimeOutput(data=runtime_result(), raw_json='{}')))
    agent = llm_agent(LearningPathAgent)
    agent.llm.chat_completion.return_value['content']['planning_rationale'] = 'P1为太阳系组成，P5为泌尿系统。'
    result = await agent.execute({'current_message': '动物皮肤导电性'}, {'turn_id': 'turn-current'})
    output = result['output']
    assert '太阳系' not in output['planning_rationale'] and '泌尿' not in output['planning_rationale']
    for stage in output['learning_path']:
        assert stage['name'] in output['planning_rationale']
        assert stage['skills'][0]['reason'] in output['planning_rationale']


@pytest.mark.asyncio
async def test_explicit_question_keeps_core_list_for_public_topic_path(monkeypatch):
    from app.services import lpp_integration
    command = AsyncMock(return_value=LppRuntimeOutput(data=runtime_result(), raw_json='{}'))
    monkeypatch.setattr(lpp_integration, '_run_lpp_command', command)
    await lpp_integration.run_lpp_for_student('43', target_question_id=500, preferred_skill_ids=[81, 82], topic_skill_ids=list(NAMES))
    arguments = command.await_args.args[0]
    assert arguments[arguments.index('--target-question-id') + 1] == '500'
    assert arguments[arguments.index('--preferred-skill-ids') + 1] == '81,82'


@pytest.mark.asyncio
async def test_extended_diagnostic_points_never_enter_planning_scope_or_its_prompt(monkeypatch):
    selected = retrieval()
    selected['matches'] = [{**m, 'relevance_tier': 'related'} for m in selected['matches']]
    selected['matches'].append({'skill_id': 253, 'skill_name': '太阳系组成', 'role': 'application', 'reason': '弱关联拓展补充', 'relevance_tier': 'extended'})
    monkeypatch.setattr('app.services.agents.learning_path.run_lpp_for_student', AsyncMock(return_value=LppRuntimeOutput(data=runtime_result(), raw_json='{}')))
    agent = llm_agent(LearningPathAgent)
    diag = kt_result()
    diag['knowledge_retrieval'] = selected
    result = await agent.execute({'current_message': '动物皮肤导电性', 'diagnosis_result': diag}, {'turn_id': 'turn-current'})
    assert 253 not in [m['skill_id'] for m in result['output']['knowledge_retrieval']['matches']]
    assert '太阳系' not in agent.llm.chat_completion.await_args.kwargs['prompt']


@pytest.mark.asyncio
async def test_diagnosis_preserves_rank_and_real_probabilities_but_explains_related_head_only(monkeypatch):
    selected = retrieval()
    selected['matches'] = [{**m, 'relevance_tier': 'related', 'relevance_rank': i + 1} for i, m in enumerate(selected['matches'])]
    selected['matches'].append({'skill_id': 253, 'skill_name': '太阳系组成', 'role': 'application', 'reason': '弱关联拓展补充', 'relevance_tier': 'extended', 'relevance_rank': 7})
    monkeypatch.setattr('app.services.agents.cognitive_diagnosis.retrieve_topic_knowledge', AsyncMock(return_value=selected))
    monkeypatch.setattr(settings.kt, 'mode', 'integrated')
    agent = llm_agent(CognitiveDiagnosisAgent)
    agent._run_kt_diagnosis = AsyncMock(return_value=kt_result())
    result = await agent.execute({'current_message': '动物皮肤导电性', 'recent_messages': []}, {'turn_id': 'turn-current'})
    states = result['output']['knowledge_states']
    assert [s['relevance_rank'] for s in states] == [1, 2, 3, 4, 5, 6, 7]
    assert states[-1]['relevance_tier'] == 'extended' and states[-1]['mastery_rate'] == .1
    prompt = agent.llm.chat_completion.await_args.kwargs['prompt']
    assert '太阳系' not in prompt and '253' not in prompt


@pytest.mark.asyncio
async def test_fixed_ranking_does_not_publish_partial_kt_predictions_as_a_complete_diagnosis(monkeypatch):
    selected = {**retrieval(), 'selection_policy': 'ranked_fixed_count'}
    monkeypatch.setattr('app.services.agents.cognitive_diagnosis.retrieve_topic_knowledge', AsyncMock(return_value=selected))
    monkeypatch.setattr(settings.kt, 'mode', 'integrated')
    agent = llm_agent(CognitiveDiagnosisAgent)
    partial = kt_result()
    partial['knowledge_states'] = partial['knowledge_states'][1:]
    agent._run_kt_diagnosis = AsyncMock(return_value=partial)
    result = await agent.execute({'current_message': '动物皮肤导电性', 'recent_messages': []}, {'turn_id': 'turn-current'})
    assert result['output']['diagnosis_source'] == 'kt_unavailable'
    assert result['output']['knowledge_states'] == []
