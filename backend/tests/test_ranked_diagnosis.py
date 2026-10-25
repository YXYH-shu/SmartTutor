"""Fixed-size diagnostic ranking with verified head and honest extensions."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import topic_retrieval as retrieval

QUERIES = {'core': ['欧姆定律中电流电压电阻的关系'], 'prerequisite': [], 'safety_ethics': [], 'application': []}
RELATED = [{'skill_id': 81, 'role': 'prerequisite', 'reason': '电阻是理解定律的直接基础'},
           {'skill_id': 52, 'role': 'prerequisite', 'reason': '导电材料是电流传导的基础'},
           {'skill_id': 82, 'role': 'core', 'reason': '直接解释电流电压电阻关系'}]
CATALOG = [{'skill_id': sid, 'skill_name': name, 'description': name + '的课程真实描述'}
           for sid, name in [(52, '导体与绝缘体'), (81, '电阻与变阻器'), (82, '欧姆定律')]
           + [(sid, f'目录项{sid}') for sid in range(101, 120)]]
ORDER = [101, 82, 81, 102, 52] + list(range(103, 116))


def client(order=ORDER):
    return SimpleNamespace(chat_completion=AsyncMock(side_effect=[
        {'content': {'queries': QUERIES, 'matches': RELATED}},
        {'content': {'queries': QUERIES, 'matches': RELATED}},
        {'content': {'ranked_matches': [{'skill_id': sid, 'reason': '该点为较弱关联的拓展诊断内容'} for sid in order]}},
    ]))


@pytest.mark.asyncio
async def test_fixed_diagnosis_has_18_unique_canonical_points_with_semantic_head_before_extensions(monkeypatch):
    monkeypatch.setattr(retrieval, 'load_topic_catalog', lambda: CATALOG)
    result = await retrieval.retrieve_topic_knowledge({'current_message': '学习欧姆定律'}, llm=client(), fill_to_limit=True)
    assert result['status'] == 'ok'
    matches = result['matches']
    assert [m['skill_id'] for m in matches] == [82, 81, 52] + list(range(101, 116))
    assert [m['relevance_rank'] for m in matches] == list(range(1, 19))
    assert [m['relevance_tier'] for m in matches] == ['related'] * 3 + ['extended'] * 15
    assert matches[0]['skill_name'] == '欧姆定律'
    assert matches[0]['reason'] == '直接解释电流电压电阻关系'
    assert result['related_count'] == 3 and result['extended_count'] == 15
    assert result['queries'] == QUERIES


@pytest.mark.asyncio
@pytest.mark.parametrize('order', [ORDER[:-1], ORDER[:-1] + [ORDER[0]], ORDER[:-1] + [9999], [101, 81, 52] + list(range(102, 117))])
async def test_invalid_rankings_fail_without_publishing_fake_fixed_18(monkeypatch, order):
    monkeypatch.setattr(retrieval, 'load_topic_catalog', lambda: CATALOG)
    result = await retrieval.retrieve_topic_knowledge({'current_message': '学习欧姆定律'}, llm=client(order), fill_to_limit=True)
    assert result['status'] == 'unavailable' and result['matches'] == []


@pytest.mark.asyncio
async def test_fixed_count_honors_small_catalog_without_duplicate_padding(monkeypatch):
    monkeypatch.setattr(retrieval, 'load_topic_catalog', lambda: CATALOG[:8])
    result = await retrieval.retrieve_topic_knowledge({'current_message': '学习欧姆定律'}, llm=client([82, 81, 52, 101, 102, 103, 104, 105]), fill_to_limit=True)
    assert len(result['matches']) == 8
    assert len({m['skill_id'] for m in result['matches']}) == 8


@pytest.mark.asyncio
async def test_ranker_uses_safe_educational_context_and_no_original_risky_request(monkeypatch):
    monkeypatch.setattr(retrieval, 'load_topic_catalog', lambda: CATALOG)
    llm = client()
    await retrieval.retrieve_topic_knowledge({'current_message': '风险原句', 'safety': {'source_branch': 'GUIDE', 'original_query': '风险原句', 'safe_query': '动物保护与电学安全', 'selected_option': '导电性科普'}}, llm=llm, fill_to_limit=True)
    prompt = llm.chat_completion.await_args_list[-1].args[0]
    assert '风险原句' not in prompt and '导电性科普' in prompt
