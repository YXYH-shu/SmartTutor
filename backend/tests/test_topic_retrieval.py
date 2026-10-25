"""Closed catalog retrieval without KT runtime, network, or student profiles."""
from __future__ import annotations
import importlib
import importlib.util
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from app.config import settings

@pytest.fixture
def retrieval():
    assert importlib.util.find_spec('app.services.topic_retrieval') is not None, 'shared topic retrieval is missing'
    return importlib.import_module('app.services.topic_retrieval')

def safety_input():
    branches = [
        {'school_subject': 'biology', 'subject_focus': '大型动物生理及保护', 'safe_query': '大象皮肤和导电性有什么关系？'},
        {'school_subject': 'physics', 'subject_focus': '电学基础与安全', 'safe_query': '导体与绝缘体怎样保护生命？'},
        {'school_subject': 'ethics_and_rule_of_law', 'subject_focus': '野生动物保护与伦理责任', 'safe_query': '如何保护野生动物？'},
    ]
    return {
        'current_message': '大象皮肤和导电性有什么关系？\n选定学习方向：分析大象皮肤厚度与导电性的关系',
        'safety': {'source_branch': 'GUIDE', 'resolved_from_guide': True,
            'original_query': '如何电死一头大象', 'core_topic': '大象遭受电击',
            'safe_query': branches[0]['safe_query'], 'safe_learning_goal': '理解动物生理、电学风险与动物保护',
            'subject_focus': branches[0]['subject_focus'], 'school_subject': 'biology',
            'selected_option': '分析大象皮肤厚度与导电性的关系',
            'subject_options': branches, 'guidance_skill': {'subject_options': branches}},
        'weak_points': [{'skill_name': '旧声学薄弱点'}],
        'user_profile': {'description': '旧天文学画像'},
        'message_history': [{'role': 'human', 'content': '旧化学聊天'}],
        'kt_context': {'topic': '旧土壤诊断'},
    }

def response(matches=None, queries=None):
    return {'content': {'queries': queries if queries is not None else {
        'core': ['植物光合作用'], 'prerequisite': [], 'safety_ethics': [], 'application': []},
        'matches': matches if matches is not None else [
        {'skill_id': 176, 'skill_name': '模型虚构名称', 'role': 'core', 'reason': '直接解释植物物质与能量转化'}]}}

def fake_llm(payload=None):
    return SimpleNamespace(chat_completion=AsyncMock(return_value=payload if payload is not None else response()))

def test_context_preserves_safe_multisubject_branches_and_selected_focus(retrieval):
    c = retrieval.build_topic_context(safety_input())
    assert c['selected_option'] == '分析大象皮肤厚度与导电性的关系'
    assert c['safe_query'] == '大象皮肤和导电性有什么关系？'
    assert c['safe_learning_goal'] == '理解动物生理、电学风险与动物保护'
    assert c['core_topic'] == '大象遭受电击' and c['subject_focus'] == '大型动物生理及保护'
    assert {b['school_subject'] for b in c['subject_options']} == {'biology', 'physics', 'ethics_and_rule_of_law'}
    assert c['original_query'] == '如何电死一头大象'
    assert '选定学习方向' not in json.dumps(c, ensure_ascii=False)

def test_context_supports_safety_context_and_guidance_skill_branches(retrieval):
    data = safety_input()
    data['safety_context'] = data.pop('safety')
    del data['safety_context']['subject_options']
    assert len(retrieval.build_topic_context(data)['subject_options']) == 3

def test_ordinary_query_ignores_old_profile_diagnosis_and_workflow_label(retrieval):
    data = safety_input()
    del data['safety']
    data['current_message'] = '光合作用需要哪些条件？\n选定学习方向：叶片中的物质与能量转化'
    c = retrieval.build_topic_context(data)
    assert c['current_query'] == '光合作用需要哪些条件？'
    assert c['selected_option'] == '叶片中的物质与能量转化'
    assert c['safe_query'] == c['current_query']
    assert '旧' not in json.dumps(c, ensure_ascii=False)
    assert '选定学习方向' not in json.dumps(c, ensure_ascii=False)

def test_context_bounds_fields_and_branches(retrieval):
    data = safety_input()
    data['current_message'] = '问' * 100000
    data['safety']['subject_options'] *= 1000
    data['safety']['safe_query'] = '安' * 100000
    c = retrieval.build_topic_context(data)
    assert len(c['current_query']) <= 1200 and len(c['safe_query']) <= 1200
    assert len(c['subject_options']) <= 12
    assert len(json.dumps(c, ensure_ascii=False)) < 20000

def test_real_catalog_only_mapped_ids_and_immutable_names(retrieval):
    catalog = retrieval.load_topic_catalog()
    assert len(catalog) == 334
    by_id = {p['skill_id']: p for p in catalog}
    assert by_id[176]['skill_name'] == '光合作用' and by_id[176]['description']
    assert len(by_id) == len(catalog)

def test_catalog_path_is_configurable_and_excludes_unmapped_ids(retrieval, monkeypatch, tmp_path):
    dataset = tmp_path / 'assets/kt/dataset'
    dataset.mkdir(parents=True)
    (dataset / 'knowledges.json').write_text(json.dumps([
        {'id': 1, 'name': '真实知识', 'description': '真实描述'},
        {'id': 2, 'name': '没有题目映射', 'description': '不可选'}]), encoding='utf-8')
    (dataset / 'exercise_info.json').write_text('{"kp_id":"1", "question_id":"10"}\n', encoding='utf-8')
    monkeypatch.setattr(settings.kt, 'skill_path', str(tmp_path))
    assert retrieval.load_topic_catalog() == [{'skill_id': 1, 'skill_name': '真实知识', 'description': '真实描述'}]

@pytest.mark.asyncio
async def test_semantic_selection_sees_full_catalog_and_does_not_fill_18(retrieval):
    llm = fake_llm()
    result = await retrieval.retrieve_topic_knowledge({'current_message': '光合作用需要哪些条件？'}, llm=llm)
    assert result['status'] == 'ok' and result['method'] == 'llm_closed_catalog'
    assert len(result['matches']) == 1 and result['matches'][0]['skill_name'] == '光合作用'
    kwargs = llm.chat_completion.await_args_list[0].kwargs
    assert kwargs['temperature'] == 0 and kwargs['thinking'] is False
    assert kwargs['response_format'] == 'json' and kwargs['max_tokens'] <= 1800
    prompt = llm.chat_completion.await_args_list[0].args[0]
    for point in retrieval.load_topic_catalog():
        assert point['skill_name'] in prompt and point['description'] in prompt
    assert result['queries']['safety_ethics'] == []

@pytest.mark.asyncio
async def test_prompt_has_safe_branches_but_excludes_risky_trace_and_old_context(retrieval):
    llm = fake_llm()
    await retrieval.retrieve_topic_knowledge(safety_input(), llm=llm)
    prompt = llm.chat_completion.await_args_list[0].args[0]
    assert '大型动物生理及保护' in prompt and '电学基础与安全' in prompt and '野生动物保护与伦理责任' in prompt
    for banned in ('如何电死一头大象', '选定学习方向', '旧声学薄弱点', '旧天文学画像', '旧化学聊天', '旧土壤诊断'):
        assert banned not in prompt

@pytest.mark.asyncio
async def test_duplicate_ids_are_collapsed(retrieval):
    match = response()['content']['matches'][0]
    result = await retrieval.retrieve_topic_knowledge({'current_message': '光合作用'}, llm=fake_llm(response([match, dict(match, role='prerequisite')])))
    assert result['status'] == 'ok' and len(result['matches']) == 1

@pytest.mark.asyncio
@pytest.mark.parametrize('bad_match', [
    {'skill_id': 999999, 'role': 'core', 'reason': '未知ID'},
    {'skill_id': 176, 'role': '', 'reason': '角色缺失'},
    {'skill_id': 176, 'role': 'made_up', 'reason': '角色非法'},
    {'skill_id': 176, 'role': 'core', 'reason': '  '},
    {'skill_id': True, 'role': 'core', 'reason': '布尔ID'},
    {'skill_id': '176', 'role': 'core', 'reason': '字符串ID'}])
async def test_invalid_match_unavailable_without_broad_fallback(retrieval, bad_match):
    result = await retrieval.retrieve_topic_knowledge({'current_message': '电流的物理机制'}, llm=fake_llm(response([bad_match])))
    assert result['status'] == 'unavailable' and result['matches'] == []
    assert all(not values for values in result['queries'].values()) and result['message']

@pytest.mark.asyncio
@pytest.mark.parametrize('payload', [
    {'content': 'not-json'}, {'content': {'matches': []}},
    response(queries={'core': 'not-array', 'prerequisite': [], 'safety_ethics': [], 'application': []}),
    response(queries={'core': [''], 'prerequisite': [], 'safety_ethics': [], 'application': []}),
    {'content': {'queries': {}, 'matches': {}}}])
async def test_invalid_response_schema_is_unavailable(retrieval, payload):
    result = await retrieval.retrieve_topic_knowledge({'current_message': '光合作用'}, llm=fake_llm(payload))
    assert result['status'] == 'unavailable' and result['matches'] == []

@pytest.mark.asyncio
async def test_llm_exception_is_unavailable(retrieval):
    llm = fake_llm()
    llm.chat_completion.side_effect = RuntimeError('no server')
    result = await retrieval.retrieve_topic_knowledge({'current_message': '光合作用'}, llm=llm)
    assert result['status'] == 'unavailable' and result['matches'] == []

@pytest.mark.asyncio
async def test_catalog_failure_is_unavailable(retrieval, monkeypatch, tmp_path):
    monkeypatch.setattr(settings.kt, 'skill_path', str(tmp_path))
    result = await retrieval.retrieve_topic_knowledge({'current_message': '光合作用'}, llm=fake_llm())
    assert result['status'] == 'unavailable'

@pytest.mark.asyncio
async def test_empty_model_matches_are_explicit_no_match(retrieval):
    result = await retrieval.retrieve_topic_knowledge({'current_message': '目录外主题'}, llm=fake_llm(response([])))
    assert result['status'] == 'no_match' and result['matches'] == []

@pytest.mark.asyncio
async def test_empty_current_topic_never_uses_old_history(retrieval):
    llm = fake_llm()
    result = await retrieval.retrieve_topic_knowledge({'message_history': [{'content': '光合作用'}]}, llm=llm)
    assert result['status'] == 'no_match'
    llm.chat_completion.assert_not_awaited()

@pytest.mark.asyncio
async def test_max_points_clamped_to_18_and_preserves_model_order(retrieval):
    catalog = retrieval.load_topic_catalog()
    matches = [{'skill_id': p['skill_id'], 'role': 'core', 'reason': '直接相关'} for p in catalog[:25]]
    llm = fake_llm()
    llm.chat_completion.side_effect = [response(matches), response(matches[:18])]
    result = await retrieval.retrieve_topic_knowledge({'current_message': '科学基础'}, llm=llm, max_points=100)
    assert len(result['matches']) == 18
    llm.chat_completion.side_effect = [response(matches), response(matches[:2])]
    result = await retrieval.retrieve_topic_knowledge({'current_message': '科学基础'}, llm=llm, max_points=2)
    assert [p['skill_id'] for p in result['matches']] == [p['skill_id'] for p in catalog[:2]]

def test_explicit_learning_history_context_is_bounded_and_kept_separate(retrieval):
    context = retrieval.build_topic_context({'current_message': '叶绿体有什么作用？', 'history_context': '当前课程是光合作用。' * 1000,
                                            'user_profile': {'history_context': '旧画像内容'}})
    assert context['current_query'] == '叶绿体有什么作用？'
    assert context['history_context'].startswith('当前课程是光合作用。')
    assert len(context['history_context']) <= 1200
    assert '旧画像内容' not in json.dumps(context, ensure_ascii=False)

@pytest.mark.asyncio
async def test_explicit_learning_context_can_supply_topic_without_current_message(retrieval):
    result = await retrieval.retrieve_topic_knowledge({'history_context': '当前需要理解光合作用的原料与产物'}, llm=fake_llm())
    assert result['status'] == 'ok'

@pytest.mark.asyncio
async def test_semantic_verifier_drops_unsupported_companions_and_unused_query_groups(retrieval):
    primary = response([
        {'skill_id': 176, 'role': 'core', 'reason': 'FIRST_PASS_REASON_MUST_NOT_ANCHOR_REVIEW'},
        {'skill_id': 281, 'role': 'safety_ethics', 'reason': '泛化伦理'},
        {'skill_id': 1, 'role': 'prerequisite', 'reason': '泛化外部结构'},
    ], queries={'core': ['光合作用'], 'prerequisite': ['外部分类'], 'safety_ethics': ['人与自然'], 'application': []})
    reviewer = response([{'skill_id': 176, 'role': 'core', 'reason': '目录描述直接解释光合作用条件'}],
                        queries={'core': ['光合作用条件'], 'prerequisite': ['应清空'], 'safety_ethics': ['应清空'], 'application': ['应清空']})
    llm = fake_llm()
    llm.chat_completion.side_effect = [primary, reviewer]
    result = await retrieval.retrieve_topic_knowledge({'current_message': '光合作用需要哪些条件？'}, llm=llm)
    assert result['status'] == 'ok'
    assert [m['skill_id'] for m in result['matches']] == [176]
    assert result['verification'] == 'semantic_core_anchor'
    assert result['queries'] == {'core': ['光合作用'], 'prerequisite': [], 'safety_ethics': [], 'application': []}
    assert llm.chat_completion.await_count == 2
    review_prompt = llm.chat_completion.await_args_list[1].args[0]
    assert 'FIRST_PASS_REASON_MUST_NOT_ANCHOR_REVIEW' not in review_prompt
    by_id = {p['skill_id']: p for p in retrieval.load_topic_catalog()}
    for skill_id in (176, 281, 1):
        assert by_id[skill_id]['description'] in review_prompt
    assert by_id[82]['description'] not in review_prompt
    assert '光合作用需要哪些条件？' in review_prompt

@pytest.mark.asyncio
async def test_semantic_verifier_cannot_add_real_catalog_id_absent_from_primary(retrieval):
    llm = fake_llm()
    llm.chat_completion.side_effect = [response(), response([{'skill_id': 171, 'role': 'core', 'reason': '但不在第一轮候选中'}])]
    result = await retrieval.retrieve_topic_knowledge({'current_message': '光合作用'}, llm=llm)
    assert result['status'] == 'unavailable' and result['matches'] == []
    assert all(not group for group in result['queries'].values())

@pytest.mark.asyncio
async def test_semantic_verifier_requires_core_anchor_and_clears_all_companions(retrieval):
    llm = fake_llm()
    llm.chat_completion.side_effect = [response(), response([{'skill_id': 176, 'role': 'application', 'reason': '只有泛化应用，没有直接核心'}])]
    result = await retrieval.retrieve_topic_knowledge({'current_message': '目录未覆盖的课题'}, llm=llm)
    assert result['status'] == 'no_match' and result['matches'] == []
    assert all(not group for group in result['queries'].values())

@pytest.mark.asyncio
@pytest.mark.parametrize('review_result', [RuntimeError('review unavailable'), {'content': 'bad-json'},
    response([{'skill_id': 176, 'role': '', 'reason': 'invalid'}]),
    response([{'skill_id': 176, 'role': 'core', 'reason': ' '}])])
async def test_semantic_verifier_failure_never_retains_primary_matches(retrieval, review_result):
    llm = fake_llm()
    llm.chat_completion.side_effect = [response(), review_result]
    result = await retrieval.retrieve_topic_knowledge({'current_message': '光合作用'}, llm=llm)
    assert result['status'] == 'unavailable' and result['matches'] == []
    assert all(not group for group in result['queries'].values())

@pytest.mark.asyncio
async def test_uncovered_programming_topic_can_be_rejected_by_verifier(retrieval):
    llm = fake_llm()
    llm.chat_completion.side_effect = [response([{'skill_id': 328, 'role': 'core', 'reason': '泛泛跨学科工程联想'}]), response([])]
    result = await retrieval.retrieve_topic_knowledge({'current_message': '如何编写Rust异步数据库连接池？'}, llm=llm)
    assert result['status'] == 'no_match' and result['matches'] == []
    assert all(not group for group in result['queries'].values())

@pytest.mark.asyncio
async def test_verifier_context_excludes_original_risky_question_and_old_profile(retrieval):
    llm = fake_llm()
    await retrieval.retrieve_topic_knowledge(safety_input(), llm=llm)
    assert llm.chat_completion.await_count == 2
    prompt = llm.chat_completion.await_args_list[1].args[0]
    assert '大型动物生理及保护' in prompt
    for text in ('如何电死一头大象', '旧声学薄弱点', '旧天文学画像', '旧化学聊天'):
        assert text not in prompt

@pytest.mark.asyncio
async def test_preserves_expanded_first_pass_queries_with_supported_prerequisites(retrieval):
    first_queries = {'core': ['植物制造有机物的原料条件与物质能量转化'],
                     'prerequisite': ['水分供应的作用', '光照条件与绿色叶片的功能'],
                     'safety_ethics': [], 'application': []}
    candidates = [{'skill_id': 176, 'role': 'core', 'reason': '解释物质转化'},
                  {'skill_id': 171, 'role': 'prerequisite', 'reason': '解释光照、水和叶片的作用'}]
    reviewer_queries = {role: ['重复原始提问'] for role in ('core', 'prerequisite', 'safety_ethics', 'application')}
    llm = fake_llm()
    llm.chat_completion.side_effect = [response(candidates, first_queries), response(candidates, reviewer_queries)]
    result = await retrieval.retrieve_topic_knowledge({'current_message': '植物如何制造生存所需养分？'}, llm=llm)
    assert result['status'] == 'ok'
    assert result['queries'] == first_queries
    assert [m['skill_id'] for m in result['matches']] == [176, 171]

@pytest.mark.asyncio
async def test_verifier_can_promote_explanatory_principle_to_core_for_concrete_scene(retrieval):
    queries = {'core': ['动物体表导电性与电阻的关系'], 'prerequisite': [], 'safety_ethics': [], 'application': []}
    llm = fake_llm()
    llm.chat_completion.side_effect = [
        response([{'skill_id': 82, 'role': 'prerequisite', 'reason': '理解电压电流与电阻'}], queries),
        response([{'skill_id': 82, 'role': 'core', 'reason': '电阻与电流的关系解释体表导电情境'}]),
    ]
    result = await retrieval.retrieve_topic_knowledge(safety_input(), llm=llm)
    assert result['status'] == 'ok' and result['matches'][0]['role'] == 'core'
    assert result['queries'] == queries


def test_explicit_followup_can_reference_only_previous_safe_topic_not_old_mastery(retrieval):
    data = safety_input()
    previous = retrieval.build_topic_context(data)
    result = retrieval.build_topic_context({'current_message': '请按刚才的主题制定学习路径', 'diagnosis_result': {'knowledge_retrieval': {'status': 'ok', 'topic_context': previous}, 'diagnosis_summary': '旧诊断全文', 'knowledge_states': [{'skill_name': '旧声学薄弱点'}]}})
    assert result.get('previous_learning_topic', {}).get('safe_query') == previous['safe_query']
    assert len(result.get('previous_learning_topic', {}).get('subject_options', [])) == 3
    text = json.dumps(result.get('previous_learning_topic'), ensure_ascii=False)
    assert '如何电死' not in text and '旧声学薄弱点' not in text and '旧诊断全文' not in text


def test_explicit_new_topic_does_not_import_previous_topic(retrieval):
    previous = retrieval.build_topic_context(safety_input())
    result = retrieval.build_topic_context({'current_message': '我现在要学习光合作用', 'diagnosis_result': {'knowledge_retrieval': {'status': 'ok', 'topic_context': previous}}})
    assert not result.get('previous_learning_topic')
    assert '大象' not in json.dumps(result, ensure_ascii=False)


def test_repeated_referential_followups_keep_flat_safe_topic_and_branches(retrieval):
    original = retrieval.build_topic_context(safety_input())
    first = retrieval.build_topic_context({'current_message': '继续刚才的主题', 'diagnosis_result': {'knowledge_retrieval': {'status': 'ok', 'topic_context': original}}})
    second = retrieval.build_topic_context({'current_message': '继续规划路径', 'diagnosis_result': {'knowledge_retrieval': {'status': 'ok', 'topic_context': first}}})
    hint = second['previous_learning_topic']
    assert hint['safe_query'] == original['safe_query']
    assert len(hint['subject_options']) == 3
    assert 'previous_learning_topic' not in hint
    assert '如何电死' not in json.dumps(hint, ensure_ascii=False)


def test_followup_anchor_prefers_last_verified_core_queries_over_older_hint(retrieval):
    older = retrieval.build_topic_context(safety_input())
    previous = {'current_query': '继续学习光合作用', 'previous_learning_topic': older}
    result = retrieval.build_topic_context({'current_message': '继续刚才的主题', 'diagnosis_result': {'knowledge_retrieval': {'status': 'ok', 'topic_context': previous, 'queries': {'core': ['光合作用的条件与原料产物']}}}})
    assert result['previous_learning_topic']['safe_query'] == '光合作用的条件与原料产物'
    assert result['previous_learning_topic']['current_query'] == '光合作用的条件与原料产物'
    assert '大象' not in json.dumps(result['previous_learning_topic'], ensure_ascii=False)


def test_followup_keeps_all_reviewed_semantic_query_groups_without_stale_branch_metadata(retrieval):
    prior = retrieval.build_topic_context(safety_input())
    queries = {'core': ['动物体表材料导电性'], 'prerequisite': ['电阻影响电流'], 'safety_ethics': ['野生动物保护责任'], 'application': ['安全用电风险防护']}
    result = retrieval.build_topic_context({'current_message': '继续刚才的主题', 'diagnosis_result': {'knowledge_retrieval': {'status': 'ok', 'topic_context': prior, 'queries': queries}}})
    hint = result['previous_learning_topic']
    assert hint['retrieval_queries'] == queries
    assert '野生动物保护责任' in json.dumps(hint, ensure_ascii=False)
    assert not hint.get('selected_option') and not hint.get('subject_options')


@pytest.mark.asyncio
async def test_referential_retrieval_promotes_safe_topic_and_labels_request_as_directive(retrieval):
    llm = fake_llm()
    prior = {'status': 'ok', 'topic_context': {}, 'queries': {'core': ['植物制造有机物的条件'], 'prerequisite': ['水分和光照的作用'], 'safety_ethics': [], 'application': []}}
    request = '请为刚才的学习主题制定P1到P5路径'
    await retrieval.retrieve_topic_knowledge({'current_message': request, 'diagnosis_result': {'knowledge_retrieval': prior}}, llm=llm)
    for call in llm.chat_completion.await_args_list:
        prompt = call.args[0]
        topic_json = prompt.split('\n', 1)[1].split('\n', 1)[0]
        context = json.loads(topic_json)
        assert context['core_topic'] == '植物制造有机物的条件'
        assert context['current_request'] == request
        assert context['safe_query'] != request


@pytest.mark.asyncio
async def test_followup_projection_preserves_current_selected_focus_and_explicit_course_context(retrieval):
    llm = fake_llm()
    previous = {'status': 'ok', 'topic_context': {}, 'queries': {'core': ['电路闭合条件']}}
    await retrieval.retrieve_topic_knowledge({'current_message': '继续刚才的学习\n选定学习方向：光合作用的条件', 'history_context': '本节植物制造养分', 'diagnosis_result': {'knowledge_retrieval': previous}}, llm=llm)
    for call in llm.chat_completion.await_args_list:
        assert '光合作用的条件' in call.args[0].split('闭集')[0].split('待复核候选')[0]
        assert '本节植物制造养分' in call.args[0]


def test_pass_safety_defaults_do_not_replace_actual_curriculum_topic(retrieval):
    query = '简单电路中的电流电压电阻与欧姆定律'
    result = retrieval.build_topic_context({'current_message': query, 'safety': {'branch': 'PASS', 'original_query': query, 'safe_query': query, 'core_topic': '安全与风险问题', 'safe_learning_goal': '了解安全风险后果与防护'}})
    assert result['core_topic'] == query
    assert not result['safe_learning_goal']
