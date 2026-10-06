"""Resolve module-function references inside named scopes without guessing methods."""

import hashlib
import io
import json
import sys
import zipfile

import pytest
from fastapi.testclient import TestClient

from openimpact.analysis.call_graph import CallGraph
from openimpact.analysis.pipeline import analyze_project
from openimpact.analysis.report import build_report
from openimpact.analysis.symbol_index import SymbolIndex
from openimpact.api import app
from openimpact.api_change import build_change_spec


def project(tmp_path, body, extra=None):
    sources = {'utils.py': 'def target(value, option=1):\n    return value\n',
               'caller.py': 'from utils import target\n' + body, **(extra or {})}
    for name, source in sources.items():
        file = tmp_path / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(source, encoding='utf-8')
    return sources


def analyze(root, config=None):
    index = SymbolIndex(root).build()
    spec = build_change_spec(index, config or {'target_symbol_id': 'utils.target',
        'change_type': 'rename_parameter', 'parameter_name': 'option', 'new_parameter_name': 'delay'})
    return analyze_project(root, spec)


@pytest.mark.parametrize('body,caller', [
    ('class Client:\n    def fetch(self):\n        return target(1, option=2)\n', 'caller.Client.fetch'),
    ('class Client:\n    async def fetch(self):\n        return target(1, option=2)\n', 'caller.Client.fetch'),
    ('def outer():\n    def inner():\n        return target(1, option=2)\n    return inner()\n', 'caller.outer.<locals>.inner'),
])
def test_named_scopes_have_real_direct_source_without_becoming_change_targets(tmp_path, body, caller):
    project(tmp_path, body)
    run = analyze(tmp_path)
    assert caller not in run.index.symbols  # No new method/nested change type.
    assert run.direct.direct_impact_count == 1
    finding = run.direct.findings[0]
    assert finding.assessment.caller_symbol_id == caller
    report = build_report(run)
    evidence = report['evidences'][0]
    assert evidence['status'] == 'available'
    assert 'target(1, option=2)' in evidence['source_snippet']
    assert evidence['source_hash'] == hashlib.sha256((tmp_path / 'caller.py').read_bytes()).hexdigest()
    assert report['explanations'][0]['evidence'] == evidence


@pytest.mark.parametrize('body', [
    'class Client:\n    def fetch(self, target):\n        return target(1, option=2)\n',
    'class Client:\n    def fetch(self):\n        target = callback\n        return target(1, option=2)\n',
    'def outer(target):\n    def inner():\n        return target(1, option=2)\n',
    'def outer():\n    target = callback\n    class Client:\n        def fetch(self):\n            return target(1, option=2)\n',
    'class Client:\n    def fetch(self):\n        try:\n            pass\n        except Exception as target:\n            return target(1, option=2)\n',
    'class Client:\n    def fetch(self, value):\n        match value:\n            case {"callback": target}:\n                return target(1, option=2)\n',
    'class Client:\n    def fetch(self):\n        from other import target\n        return target(1, option=2)\n',
    'def outer():\n    def inner(value=(target := callback)):\n        return target(1, option=2)\n',
    'def outer():\n    class Client(target := callback):\n        def fetch(self):\n            return target(1, option=2)\n',
    'def outer():\n    factory = lambda value=(target := callback): value\n    def inner():\n        return target(1, option=2)\n',
])
def test_local_closure_import_exception_and_pattern_bindings_are_never_guessed(tmp_path, body):
    project(tmp_path, body)
    run = analyze(tmp_path)
    assert run.direct.direct_impact_count == 0
    assert any(c.reason == 'local_name_shadows_target' for c in run.graph.unresolved_calls)
    assert build_report(run)['coverage']['status'] == 'partial'


def test_class_namespace_is_not_a_method_closure(tmp_path):
    project(tmp_path, 'class Client:\n    target = unrelated\n'
        '    def fetch(self):\n        return target(1, option=2)\n')
    assert analyze(tmp_path).direct.direct_impact_count == 1


def test_implicit_class_cell_cannot_be_mistaken_for_an_imported_function(tmp_path):
    project(tmp_path, '')
    (tmp_path / 'caller.py').write_text('from utils import target as __class__\n'
        'class Client:\n    def fetch(self):\n        return __class__(1, option=2)\n', encoding='utf-8')
    assert analyze(tmp_path).direct.direct_impact_count == 0


def test_method_dispatch_is_not_inferred_from_self_or_a_class_name(tmp_path):
    project(tmp_path, 'class Client:\n    def fetch(self):\n        return target(1, option=2)\n'
        '    def run(self):\n        return self.fetch()\n'
        'def invoke(client):\n    return client.fetch()\n')
    run = analyze(tmp_path)
    assert run.direct.direct_impact_count == 1
    assert not run.indirect.findings
    assert {'self.fetch', 'client.fetch'} <= {c.call.expression for c in run.graph.unresolved_calls}


def test_existing_reverse_graph_can_reach_a_method_calling_a_module_wrapper(tmp_path):
    project(tmp_path, 'def wrapper():\n    return target(1, option=2)\n'
        'class Client:\n    def fetch(self):\n        return wrapper()\n')
    run = analyze(tmp_path)
    assert run.direct.direct_impact_count == 1
    assert [(f.impacted_symbol_id, f.impact_type) for f in run.indirect.findings] == [
        ('caller.Client.fetch', 'indirect_1hop')]
    report = build_report(run)
    assert report['evidences'][1]['propagation_path'][0]['symbols'] == [
        'caller.Client.fetch', 'caller.wrapper', 'utils.target']


def test_duplicate_named_methods_cannot_create_certain_edges(tmp_path):
    project(tmp_path, 'class Client:\n    def fetch(self):\n        return target(1, option=2)\n'
        '    def fetch(self):\n        return target(2, option=3)\n')
    run = analyze(tmp_path)
    assert run.direct.direct_impact_count == 0
    assert all(c.reason == 'caller_not_indexed' for c in run.graph.unresolved_calls)


def test_lambda_and_class_body_have_separate_source_contexts(tmp_path):
    project(tmp_path, 'class Client:\n    value = target(1, option=2)\n'
        '    def fetch(self):\n        return target(1, option=2)\n'
        'callback = lambda: target(1, option=2)\n')
    report = build_report(analyze(tmp_path))
    assert report['summary']['direct_impact_count'] == 3
    assert report['coverage']['status'] == 'complete'
    assert not report['diagnostics'].get('unsupported_scopes')
    assert len({item['caller_symbol_id'] for item in report['direct_impacts']}) == 3
    assert len(report['evidences']) == 3


def test_explicit_dotted_module_import_supports_qualified_calls(tmp_path):
    project(tmp_path, 'def call():\n    return pkg.utils.target(1, option=2)\n',
        {'pkg/__init__.py': '', 'pkg/utils.py': 'def target(value, option=1):\n    return value\n'})
    (tmp_path / 'caller.py').write_text('import pkg.utils\ndef call():\n'
        '    return pkg.utils.target(1, option=2)\n', encoding='utf-8')
    run = analyze(tmp_path, {'target_symbol_id': 'pkg.utils.target', 'change_type': 'rename_parameter',
        'parameter_name': 'option', 'new_parameter_name': 'delay'})
    assert run.direct.direct_impact_count == 1


def test_package_import_alone_does_not_prove_a_child_attribute(tmp_path):
    project(tmp_path, 'def call():\n    return pkg.utils.target(1, option=2)\n',
        {'pkg/__init__.py': '', 'pkg/utils.py': 'def target(value, option=1):\n    return value\n'})
    (tmp_path / 'caller.py').write_text('import pkg\ndef call():\n'
        '    return pkg.utils.target(1, option=2)\n', encoding='utf-8')
    assert not CallGraph(SymbolIndex(tmp_path).build()).build().edges


@pytest.mark.parametrize('assignment,initializer', [
    ('pkg.utils = replacement\n', ''),
    ('del pkg.utils\n', ''),
    ('pkg.utils.target = replacement\n', ''),
    ('', 'utils = replacement\n'),
])
def test_dotted_import_attribute_overwrites_are_not_proven_bindings(tmp_path, assignment, initializer):
    project(tmp_path, '', {'pkg/__init__.py': initializer,
        'pkg/utils.py': 'def target(value, option=1):\n    return value\n'})
    (tmp_path / 'caller.py').write_text('import pkg.utils\n' + assignment +
        'def call():\n    return pkg.utils.target(1, option=2)\n', encoding='utf-8')
    assert not CallGraph(SymbolIndex(tmp_path).build()).build().edges


@pytest.mark.skipif(sys.version_info < (3, 12), reason='PEP 695 syntax requires Python 3.12')
def test_generic_class_type_parameter_is_not_the_global_function(tmp_path):
    project(tmp_path, 'class Client[target]:\n    def fetch(self):\n        return target(1, option=2)\n')
    assert analyze(tmp_path).direct.direct_impact_count == 0


def test_scoped_reference_works_through_zip_validate_analyze_and_fingerprint(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENIMPACT_LLM_PROVIDER', 'rule')
    sources = project(tmp_path, 'class Client:\n    def fetch(self):\n        return target(1, option=2)\n')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        for name, source in sources.items():
            archive.writestr(name, source)
    data = buffer.getvalue()
    files = {'file': ('project.zip', data, 'application/zip')}
    with TestClient(app) as client:
        inspect = client.post('/api/v1/projects/inspect', files=files).json()
        assert all('Client.fetch' not in s['symbol_id'] for s in inspect['symbols'])
        fields = {'expected_fingerprint': inspect['project_fingerprint'], 'change': json.dumps({
            'target_symbol_id': 'utils.target', 'change_type': 'rename_parameter',
            'parameter_name': 'option', 'new_parameter_name': 'delay'})}
        assert client.post('/api/v1/changes/validate', files=files, data=fields).status_code == 200
        response = client.post('/api/v1/projects/analyze', files=files, data=fields)
        assert response.status_code == 200
        assert response.json()['summary']['direct_impact_count'] == 1
        fields['expected_fingerprint'] = '0' * 64
        assert client.post('/api/v1/projects/analyze', files=files, data=fields).status_code == 409


@pytest.mark.parametrize('operation,call', [
    ({'added_parameter': {'name': 'strict', 'kind': 'keyword_only'}}, 'target(1, option=2)'),
    ({'change_type': 'remove_parameter', 'parameter_name': 'option'}, 'target(1, option=2)'),
    ({'change_type': 'rename_parameter', 'parameter_name': 'option', 'new_parameter_name': 'delay'}, 'target(1, option=2)'),
    ({'change_type': 'make_parameter_required', 'parameter_name': 'option'}, 'target(1)'),
])
def test_all_four_operations_use_the_unchanged_compatibility_engine_in_methods(tmp_path, operation, call):
    project(tmp_path, f'class Client:\n    def fetch(self):\n        return {call}\n')
    run = analyze(tmp_path, {'target_symbol_id': 'utils.target', **operation})
    assert run.direct.direct_impact_count == 1
    assert [(a.before_status, a.after_status) for a in run.direct.assessments] == [('compatible', 'incompatible')]


@pytest.mark.parametrize('operation,call,effect', [
    ({'change_type': 'rename_parameter', 'parameter_name': 'option', 'new_parameter_name': 'delay'}, 'target(1, 2)', 'no_impact'),
    ({'change_type': 'make_parameter_required', 'parameter_name': 'option'}, 'target(1, option=2)', 'no_impact'),
    ({'change_type': 'rename_parameter', 'parameter_name': 'option', 'new_parameter_name': 'delay'}, 'target(unknown=2)', 'pre_existing_problem'),
    ({'change_type': 'rename_parameter', 'parameter_name': 'option', 'new_parameter_name': 'delay'}, 'target(*values, **options)', 'manual_review'),
])
def test_new_callers_preserve_negative_preexisting_and_star_policies(tmp_path, operation, call, effect):
    project(tmp_path, f'class Client:\n    def fetch(self, values, options):\n        return {call}\n')
    run = analyze(tmp_path, {'target_symbol_id': 'utils.target', **operation})
    assert run.direct.direct_impact_count == 0
    assert [a.effect for a in run.direct.assessments] == [effect]
    assert not run.indirect.findings
