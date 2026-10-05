"""Explanations check real positions, preserve analysis, and disclose missing facts."""

from dataclasses import replace
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from openimpact.analysis.change_file import load_change_spec
from openimpact.analysis.pipeline import analyze_project
from openimpact.analysis.report import build_report
from openimpact.explanation.context import build_explanation_context
from openimpact.explanation.deepseek import _build_messages, DeepSeekProvider
from openimpact.explanation.models import ExplanationInput, fallback_explanation
from openimpact.explanation.provider import ExplanationProvider
from openimpact.reporting.evidence import EvidenceBuilder

EXAMPLES = Path(__file__).resolve().parents[2] / 'examples'


def run_demo(name='signature_change', root=None):
    project = root or EXAMPLES / name
    return analyze_project(project, load_change_spec(EXAMPLES / name / 'change.json'))


def input_for(run, finding):
    evidence = EvidenceBuilder(run.project_path).build(finding)
    return replace(ExplanationInput.from_evidence(evidence, run.change_spec.describe()),
                   context=build_explanation_context(run, finding, evidence))


def test_context_contains_exact_sites_and_canonical_signatures():
    run = run_demo()
    data = input_for(run, run.indirect.findings[-1])
    context = data.context
    assert [(step.file, step.line, step.column) for step in context.steps] == [
        ('page.py', 5, 11), ('dashboard.py', 5, 11), ('report.py', 5, 11)]
    assert context.steps[-1].expression == 'format_date(date)'
    assert all(len(step.source_hash) == 64 for step in context.steps)
    assert context.before_signature == run.change_spec.before_signature
    assert context.after_signature == run.change_spec.after_signature
    assert context.after_reason == run.direct.assessments[0].after_reason
    suggestion = fallback_explanation(data).suggested_check
    assert suggestion.index('report.py:5:11') < suggestion.index('dashboard.py:5:11') < suggestion.index('page.py:5:11')
    assert '未被判定为参数不兼容' in suggestion
    assert '值的来源需人工确认' in suggestion
    assert '测试位置和执行结果未提供' in suggestion


@pytest.mark.parametrize('name,phrase', [
    ('signature_change', '新增参数所需信息'),
    ('parameter_removal', '被删除参数所承载的信息'),
    ('parameter_rename_keyword', '旧参数名'),
    ('parameter_required_missing', '原默认值'),
])
def test_check_advice_matches_actual_operation(name, phrase):
    report = build_report(run_demo(name))
    assert report['summary']['direct_impact_count'] == 1
    assert phrase in report['explanations'][0]['explanation']['suggested_check']
    assert report['explanations'][0]['explanation']['risk_level'] == 'unknown'


def test_context_mismatch_rejected_without_rebinding():
    run = run_demo()
    data = input_for(run, run.direct.findings[0])
    wrong = replace(data.context.steps[0], file='other.py')
    with pytest.raises(ValueError, match='不对应'):
        replace(data, context=replace(data.context, steps=(wrong,)))
    with pytest.raises(ValueError, match='相对路径'):
        replace(data.context.steps[0], file='../outside.py')


@pytest.mark.parametrize('missing', [True, False])
def test_terminal_source_missing_or_changed_does_not_invent_old_expression(tmp_path, missing):
    for path in (EXAMPLES / 'signature_change').glob('*.py'):
        (tmp_path / path.name).write_bytes(path.read_bytes())
    run = run_demo(root=tmp_path)
    if missing:
        (tmp_path / 'report.py').unlink()
    else:
        (tmp_path / 'report.py').write_text('from utils import format_date\n\ndef report(date):\n    pass\n', encoding='utf-8')
    data = input_for(run, run.indirect.findings[-1])
    assert data.context.steps[-1].expression is None
    text = fallback_explanation(data).suggested_check
    assert '源码未能复核' in text
    assert 'format_date(date)' not in text


def test_context_failure_preserves_all_analysis_and_base_explanation():
    run = run_demo()
    good = build_report(run)
    with patch('openimpact.analysis.report.build_explanation_context', side_effect=RuntimeError('context failed')):
        failed = build_report(run)
    assert {k: v for k, v in good.items() if k != 'explanations'} == {k: v for k, v in failed.items() if k != 'explanations'}
    assert all(record['explanation'] for record in failed['explanations'])


def test_prompt_receives_bounded_context_and_mock_failure_uses_rich_fallback():
    run = run_demo()
    data = input_for(run, run.indirect.findings[-1])
    messages = _build_messages(data)
    payload = json.loads(messages[1]['content'])
    assert len(payload['context']['steps']) == 3
    assert payload['context']['steps'][-1]['expression'] == 'format_date(date)'
    assert '不得推断参数值来源' in messages[0]['content']
    assert str(run.project_path) not in messages[1]['content']
    provider = DeepSeekProvider(api_key='test-key')
    with patch.object(provider, '_request_completion', return_value='invalid json'):
        result = provider.explain(data)
    assert provider.last_call.status == 'fallback'
    assert result == fallback_explanation(data)


def test_partial_context_discloses_limits_without_changing_impact(tmp_path):
    for path in (EXAMPLES / 'signature_change').glob('*.py'):
        (tmp_path / path.name).write_bytes(path.read_bytes())
    (tmp_path / 'broken.py').write_text('def broken(:', encoding='utf-8')
    report = build_report(run_demo(root=tmp_path))
    assert report['coverage']['status'] == 'partial'
    assert report['summary']['direct_impact_count'] == 1
    assert '不能代表整个项目' in report['explanations'][0]['explanation']['suggested_check']


def test_multiple_seeds_keep_representative_path_and_disclose_other_sources(tmp_path):
    (tmp_path / 'utils.py').write_text('def format_date(date):\n    return date\n', encoding='utf-8')
    (tmp_path / 'report.py').write_text('from utils import format_date\ndef report(date):\n    format_date(date)\n    return format_date(date)\n', encoding='utf-8')
    (tmp_path / 'page.py').write_text('from report import report\ndef page():\n    return report(1)\n', encoding='utf-8')
    run = run_demo(root=tmp_path)
    data = input_for(run, run.indirect.findings[0])
    assert data.context.path_count == 2
    assert len(data.context.steps) == 2
    assert '2 个直接影响来源' in fallback_explanation(data).suggested_check


def test_recording_provider_gets_context_without_any_new_public_result_fields():
    seen = []
    class RecordingProvider(ExplanationProvider):
        def explain(self, input):
            seen.append(input)
            return fallback_explanation(input)
    report = build_report(run_demo(), explanation_provider=RecordingProvider())
    assert all(item.context is not None for item in seen)
    assert all(set(item['explanation']) == {'summary', 'why_affected', 'risk_level', 'suggested_check', 'confidence'}
               for item in report['explanations'])


def test_mock_model_success_keeps_every_static_report_field_and_source_bytes():
    run = run_demo()
    before = {file.name: file.read_bytes() for file in run.project_path.glob('*.py')}
    baseline = build_report(run)
    provider = DeepSeekProvider(api_key='test-key')
    result = {'summary': '沿当前证据检查。', 'why_affected': '原始直接调用的兼容性发生变化。',
              'risk_level': 'unknown', 'suggested_check': '先核对已有直接调用位置，再检查上游。', 'confidence': .8}
    with patch.object(provider, '_request_completion', return_value=json.dumps(result, ensure_ascii=False)):
        model = build_report(run, explanation_provider=provider)
    assert provider.last_call.status == 'model_success'
    assert {k: v for k, v in baseline.items() if k != 'explanations'} == {k: v for k, v in model.items() if k != 'explanations'}
    assert before == {file.name: file.read_bytes() for file in run.project_path.glob('*.py')}


def test_multiline_call_with_chinese_binding_preserves_utf8_column(tmp_path):
    (tmp_path / 'utils.py').write_text('def format_date(date):\n    return date\n', encoding='utf-8')
    (tmp_path / 'report.py').write_text('from utils import format_date\ndef report(date):\n    结果 = format_date(\n        date)\n    return 结果\n', encoding='utf-8')
    run = run_demo(root=tmp_path)
    step = input_for(run, run.direct.findings[0]).context.steps[0]
    assert step.column == 13
    assert step.expression == 'format_date(\n        date)'
