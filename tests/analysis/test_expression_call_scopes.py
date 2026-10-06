"""Class/lambda calls use real binding facts, never assumed callback invocation."""

import hashlib
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from openimpact.analysis.ast_parser import ASTParser
from openimpact.analysis.pipeline import analyze_project
from openimpact.analysis.report import build_report
from openimpact.analysis.symbol_index import SymbolIndex
from openimpact.api import app
from openimpact.api_change import build_change_spec


def run_project(root, body, operation=None):
    (root / 'utils.py').write_text('def target(value, option=1):\n    return value\n', encoding='utf-8')
    (root / 'caller.py').write_text('from utils import target\n' + body, encoding='utf-8')
    index = SymbolIndex(root).build()
    spec = build_change_spec(index, {'target_symbol_id': 'utils.target', **(operation or {
        'change_type': 'rename_parameter', 'parameter_name': 'option', 'new_parameter_name': 'delay'})})
    return analyze_project(root, spec)


@pytest.mark.parametrize('body,context,line', [
    ('class Client:\n    value = target(1, option=2)\n', 'Client.<class_body@2:0>', 3),
    ('class Client:\n    def fetch(self, value=target(1, option=2)):\n        return value\n', 'Client.<class_body@2:0>', 3),
    ('callback = lambda: target(1, option=2)\n', '<lambda@2:11>', 2),
    ('def outer():\n    return lambda: target(1, option=2)\n', 'outer.<lambda@3:11>', 3),
    ('class Client:\n    callback = lambda: target(1, option=2)\n', 'Client.<lambda@3:15>', 3),
])
def test_new_contexts_have_exact_call_evidence_and_are_not_change_targets(tmp_path, body, context, line):
    run = run_project(tmp_path, body)
    assert set(run.index.symbols) == {'utils.target'} | ({'caller.outer'} if 'def outer' in body else set())
    assert run.direct.direct_impact_count == 1
    assert run.direct.assessments[0].caller_symbol_id == 'caller.' + context
    assert run.direct.assessments[0].line == line
    assert not run.indirect.findings  # Defining a class/callback adds no invocation edge.
    report = build_report(run)
    evidence = report['evidences'][0]
    assert evidence['status'] == 'available'
    assert evidence['location']['file'] == 'caller.py'
    assert 'target(1, option=2)' in evidence['source_snippet']
    assert evidence['source_hash'] == hashlib.sha256((tmp_path / 'caller.py').read_bytes()).hexdigest()
    assert report['explanations'][0]['evidence'] == evidence


@pytest.mark.parametrize('body', [
    'callback = lambda target: target(1, option=2)\n',
    'callback = lambda: ((target := callback), target(1, option=2))\n',
    'def outer(target):\n    return lambda: target(1, option=2)\n',
    'class Client:\n    target = callback\n    value = target(1, option=2)\n',
    'class Client:\n    from other import target\n    value = target(1, option=2)\n',
    'class Client:\n    target = callback\n    def fetch(self, value=target(1, option=2)):\n        return value\n',
    'class Client:\n    callbacks = [lambda: target(1, option=2) for target in callbacks]\n',
    'class Client:\n    value = [target(1, option=2) for target in callbacks]\n',
    'def outer(target):\n    class Client:\n        value = target(1, option=2)\n',
])
def test_shadowed_class_lambda_and_comprehension_names_are_never_guessed(tmp_path, body):
    run = run_project(tmp_path, body)
    assert run.direct.direct_impact_count == 0
    assert any(call.reason == 'local_name_shadows_target' for call in run.graph.unresolved_calls)
    assert build_report(run)['coverage']['status'] == 'partial'


def test_class_attributes_are_not_lambda_or_method_closure_bindings(tmp_path):
    run = run_project(tmp_path, 'class Client:\n    target = callback\n'
        '    callback = lambda: target(1, option=2)\n'
        '    def fetch(self):\n        return target(1, option=2)\n')
    assert run.direct.direct_impact_count == 2


@pytest.mark.parametrize('header', ['class Client(Base):', 'class Client(metaclass=Meta):'])
def test_uncertain_class_namespace_is_collected_with_explicit_diagnostic(tmp_path, header):
    run = run_project(tmp_path, header + '\n    value = target(1, option=2)\n')
    assert run.direct.direct_impact_count == 0
    assert [call.reason for call in run.graph.unresolved_calls] == ['class_namespace_unresolved']
    assert not run.index.unsupported_scope_diagnostics()


def test_dynamic_class_namespace_is_not_used_to_prove_a_global_call(tmp_path):
    run = run_project(tmp_path, 'class Client:\n    locals().update(callbacks)\n'
        '    value = target(1, option=2)\n')
    assert run.direct.direct_impact_count == 0
    assert any(call.reason == 'class_namespace_unresolved' for call in run.graph.unresolved_calls)


@pytest.mark.parametrize('source', [
    'class Client:\n    value = target(1, option=2)\nfrom utils import target\n',
    'class Client:\n    value = target(1, option=2)\ndef target(value, option=1):\n    return value\n',
])
def test_eager_class_body_cannot_bind_to_a_later_import_or_definition(tmp_path, source):
    run_project(tmp_path, '')
    (tmp_path / 'caller.py').write_text(source, encoding='utf-8')
    index = SymbolIndex(tmp_path).build()
    spec = build_change_spec(index, {'target_symbol_id': 'utils.target' if 'from utils' in source else 'caller.target',
        'change_type': 'rename_parameter', 'parameter_name': 'option', 'new_parameter_name': 'delay'})
    run = analyze_project(tmp_path, spec)
    assert run.direct.direct_impact_count == 0
    assert [call.reason for call in run.graph.unresolved_calls] == ['call_before_binding']


def test_class_inside_deferred_function_does_not_assume_module_definition_order(tmp_path):
    run = run_project(tmp_path, 'def factory():\n    class Client:\n        value = target(1, option=2)\n'
        '    return Client\n')
    assert run.direct.direct_impact_count == 1


@pytest.mark.parametrize('statement,expression', [
    ('import utils as u', 'u.target'),
    ('from utils import target as t', 't'),
])
@pytest.mark.parametrize('template', ['class Client:\n    value = {expression}(1, option=2)\n',
                                     'callback = lambda: {expression}(1, option=2)\n'])
def test_import_aliases_keep_real_module_binding_in_new_scopes(tmp_path, statement, expression, template):
    run_project(tmp_path, '')
    (tmp_path / 'caller.py').write_text(statement + '\n' + template.format(expression=expression), encoding='utf-8')
    index = SymbolIndex(tmp_path).build()
    spec = build_change_spec(index, {'target_symbol_id': 'utils.target', 'change_type': 'rename_parameter',
        'parameter_name': 'option', 'new_parameter_name': 'delay'})
    assert analyze_project(tmp_path, spec).direct.direct_impact_count == 1


def test_eager_dotted_import_cannot_resolve_a_later_binding(tmp_path):
    (tmp_path / 'pkg').mkdir()
    (tmp_path / 'pkg/__init__.py').write_text('', encoding='utf-8')
    (tmp_path / 'pkg/utils.py').write_text('def target(value, option=1):\n    return value\n', encoding='utf-8')
    (tmp_path / 'caller.py').write_text('class Client:\n    value = pkg.utils.target(1, option=2)\n'
        'import pkg.utils\n', encoding='utf-8')
    index = SymbolIndex(tmp_path).build()
    spec = build_change_spec(index, {'target_symbol_id': 'pkg.utils.target', 'change_type': 'rename_parameter',
        'parameter_name': 'option', 'new_parameter_name': 'delay'})
    run = analyze_project(tmp_path, spec)
    assert run.direct.direct_impact_count == 0
    assert [c.reason for c in run.graph.unresolved_calls] == ['call_before_binding']


def test_two_lambdas_on_one_line_and_repeated_class_definitions_have_distinct_ids(tmp_path):
    run = run_project(tmp_path, 'callbacks = (lambda: target(1, option=2), lambda: target(2, option=3))\n'
        'class Client:\n    value = target(1, option=2)\n'
        'class Client:\n    value = target(1, option=2)\n')
    assert run.direct.direct_impact_count == 4
    assert len({item.caller_symbol_id for item in run.direct.assessments}) == 4
    assert not run.indirect.findings


def test_defaults_remain_in_parent_scope_and_lambda_body_in_its_own_scope(tmp_path):
    run = run_project(tmp_path, 'class Client:\n'
        '    callback = lambda value=target(1, option=2): target(value, option=3)\n')
    assert run.direct.direct_impact_count == 2
    assert len({item.caller_symbol_id for item in run.direct.assessments}) == 2


@pytest.mark.parametrize('operation,call,effect', [
    ({'added_parameter': {'name': 'strict', 'kind': 'keyword_only'}}, 'target(1)', 'direct_impact'),
    ({'change_type': 'remove_parameter', 'parameter_name': 'option'}, 'target(1, option=2)', 'direct_impact'),
    ({'change_type': 'rename_parameter', 'parameter_name': 'option', 'new_parameter_name': 'delay'}, 'target(1, option=2)', 'direct_impact'),
    ({'change_type': 'make_parameter_required', 'parameter_name': 'option'}, 'target(1)', 'direct_impact'),
    ({'change_type': 'rename_parameter', 'parameter_name': 'option', 'new_parameter_name': 'delay'}, 'target(1, 2)', 'no_impact'),
    ({'change_type': 'rename_parameter', 'parameter_name': 'option', 'new_parameter_name': 'delay'}, 'target(unknown=2)', 'pre_existing_problem'),
    ({'change_type': 'rename_parameter', 'parameter_name': 'option', 'new_parameter_name': 'delay'}, 'target(1, delay=2)', 'compatibility_improved'),
    ({'change_type': 'rename_parameter', 'parameter_name': 'option', 'new_parameter_name': 'delay'}, 'target(*values, **options)', 'manual_review'),
])
@pytest.mark.parametrize('template', ['class Client:\n    value = {call}\n', 'callback = lambda: {call}\n'])
def test_existing_compatibility_policy_is_shared_by_both_new_contexts(tmp_path, operation, call, effect, template):
    run = run_project(tmp_path, template.format(call=call), operation)
    assert [item.effect for item in run.direct.assessments] == [effect]
    assert run.direct.direct_impact_count == int(effect == 'direct_impact')


def test_upstream_scopes_use_real_call_edges_without_fabricated_enclosing_edges(tmp_path):
    run = run_project(tmp_path, 'def wrapper():\n    return target(1, option=2)\n'
        'class Client:\n    value = wrapper()\n'
        'callback = lambda: wrapper()\n'
        'def outer():\n    return lambda: target(1, option=2)\n')
    assert run.direct.direct_impact_count == 2
    assert len(run.indirect.findings) == 2
    assert all(f.impact_type == 'indirect_1hop' for f in run.indirect.findings)
    assert all(len(f.sources[0].propagation_path) == 2 for f in run.indirect.findings)
    assert all(f.impacted_symbol_id != 'caller.outer' for f in run.indirect.findings)


def test_parser_accounts_for_every_syntactic_call_once(tmp_path):
    run_project(tmp_path, 'class Client:\n    callback = lambda value=target(1): target(value)\n'
        '    def fetch(self, value=target(1)):\n        return target(value)\n')
    parsed = ASTParser(tmp_path / 'caller.py').parse()
    assert len(parsed.calls) == 4
    assert len({(c.lineno, c.col_offset) for c in parsed.calls}) == 4
    assert not parsed.unsupported_call_scopes


def test_zip_workflow_exposes_new_evidence_without_changing_symbol_candidates(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENIMPACT_LLM_PROVIDER', 'rule')
    run_project(tmp_path, 'class Client:\n    value = target(1, option=2)\n'
        'callback = lambda: target(1, option=2)\n')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        for path in sorted(tmp_path.glob('*.py')):
            archive.writestr(path.name, path.read_bytes())
    files = {'file': ('project.zip', buffer.getvalue(), 'application/zip')}
    with TestClient(app) as client:
        inspection = client.post('/api/v1/projects/inspect', files=files).json()
        assert [item['symbol_id'] for item in inspection['symbols']] == ['utils.target']
        data = {'expected_fingerprint': inspection['project_fingerprint'], 'change': json.dumps({
            'target_symbol_id': 'utils.target', 'change_type': 'rename_parameter',
            'parameter_name': 'option', 'new_parameter_name': 'delay'})}
        assert client.post('/api/v1/changes/validate', files=files, data=data).status_code == 200
        response = client.post('/api/v1/projects/analyze', files=files, data=data)
        assert response.status_code == 200
        assert response.json()['summary']['direct_impact_count'] == 2
        assert response.json()['coverage']['status'] == 'complete'
        data['expected_fingerprint'] = '0' * 64
        assert client.post('/api/v1/projects/analyze', files=files, data=data).status_code == 409
