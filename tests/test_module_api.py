"""Real ZIP HTTP workflow, conservative coverage and request snapshot safety."""
import hashlib
import io
import json
import zipfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from openimpact.api import app
from openimpact.repository import zip_inspector


def archive(files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as package:
        for name, source in files.items():
            package.writestr(name, source)
    return stream.getvalue()


def request(client, path, data, change=None, fingerprint=None):
    fields = {} if change is None else {'change': json.dumps(change) if isinstance(change, dict) else change}
    if fingerprint is not None:
        fields['expected_fingerprint'] = fingerprint
    return client.post('/api/v1/' + path, data=fields,
                       files={'file': ('project.zip', data, 'application/zip')})


@pytest.mark.parametrize('kind', ['rename_module', 'remove_module'])
def test_module_three_step_workflow_and_cleanup(kind, monkeypatch):
    demo = Path(__file__).resolve().parents[1] / 'examples/module_rename'
    data = archive({p.name: p.read_bytes() for p in demo.glob('*.py')})
    change = {'change_domain': 'module', 'change_type': kind, 'target_module_id': 'utils'}
    if kind == 'rename_module':
        change['new_module_name'] = 'formatting'
    locations = []
    original = zip_inspector.TemporaryDirectory
    def record(*args, **kwargs):
        directory = original(*args, **kwargs)
        locations.append(Path(directory.name))
        return directory
    monkeypatch.setattr(zip_inspector, 'TemporaryDirectory', record)
    with TestClient(app) as client:
        inspect = request(client, 'projects/inspect', data).json()
        assert {m['module_id'] for m in inspect['module_inventory']['modules']} == {'utils', 'report', 'dashboard', 'page'}
        fingerprint = inspect['project_fingerprint']
        assert fingerprint == hashlib.sha256(data).hexdigest()
        validated = request(client, 'changes/validate', data, change, fingerprint)
        assert validated.status_code == 200, validated.text
        analyzed = request(client, 'projects/analyze', data, change, fingerprint)
        assert analyzed.status_code == 200, analyzed.text
    body = analyzed.json()
    assert body['change'] == validated.json()['change_spec']
    assert body['change_domain'] == 'module' and body['schema_version'] == 1
    assert body['summary']['direct_import_count'] == 1
    assert body['summary']['indirect_1hop_module_count'] == 1
    assert body['summary']['indirect_2hop_module_count'] == 1
    assert body['coverage']['status'] == 'complete'
    assert body['project_fingerprint'] == fingerprint
    assert body['evidences'][2]['propagation_path'][0]['modules'] == ['page', 'dashboard', 'report', 'utils']
    assert all(e['evidence_reference'] == x['evidence_reference'] for e, x in zip(body['evidences'], body['explanations']))
    assert 'direct_impacts' not in body and 'before_signature' not in body['change']
    assert len(locations) == 3 and all(not p.exists() for p in locations)
    assert all(str(p) not in json.dumps(body) for p in locations)


@pytest.mark.parametrize('extra', ['formatting/', 'formatting.py', 'Formatting/', 'formatting/data.txt', 'Formatting.PY'])
def test_rename_conflict_checks_unextracted_zip_entries(extra):
    data = archive({'utils.py': 'x = 1', extra: ''})
    change = {'change_domain': 'module', 'change_type': 'rename_module', 'target_module_id': 'utils', 'new_module_name': 'formatting'}
    with TestClient(app) as client:
        response = request(client, 'changes/validate', data, change)
    assert response.status_code == 422
    assert response.json()['validation']['diagnostics'][0]['code'] == 'module_name_conflict'


@pytest.mark.parametrize('target,new_name', [('missing', 'next_module'), ('utils', '../escape'), ('utils', 'utils'), ('utils', 'os')])
def test_invalid_config_is_422(target, new_name):
    with TestClient(app) as client:
        response = request(client, 'changes/validate', archive({'utils.py': 'x=1'}),
                           {'change_domain': 'module', 'change_type': 'rename_module', 'target_module_id': target, 'new_module_name': new_name})
    assert response.status_code == 422 and response.json()['validation']['valid'] is False


def test_module_partial_coverage_and_unknown_not_direct():
    data = archive({'utils.py': 'def f(): pass', 'report.py': 'from utils import f\nimport external\nif True:\n import utils\n',
                    'broken.py': 'def bad(:', 'dynamic.py': '__import__("utils")'})
    with TestClient(app) as client:
        response = request(client, 'projects/analyze', data, {'change_domain': 'module', 'change_type': 'remove_module', 'target_module_id': 'utils'})
    assert response.status_code == 200
    body = response.json()
    assert body['coverage']['status'] == 'partial'
    assert body['summary']['direct_import_count'] == 1
    assert body['summary']['manual_review_count'] == 2
    assert body['summary']['unresolved_import_count'] == 1
    assert body['diagnostics']['parse_errors']


def test_module_failure_cleanup_safe_500_and_fingerprint_gate(monkeypatch):
    import openimpact.api as api
    data = archive({'utils.py': 'raise RuntimeError("do not execute")'})
    config = {'change_domain': 'module', 'change_type': 'remove_module', 'target_module_id': 'utils'}
    locations = []
    original = zip_inspector.TemporaryDirectory
    def record(*args, **kwargs):
        directory = original(*args, **kwargs); locations.append(Path(directory.name)); return directory
    monkeypatch.setattr(zip_inspector, 'TemporaryDirectory', record)
    def fail(*args):
        raise RuntimeError('SECRET/internal/path')
    monkeypatch.setattr(api, 'analyze_module_project', fail)
    with TestClient(app) as client:
        assert request(client, 'projects/analyze', data, config, '0' * 64).status_code == 409
        assert not locations
        response = request(client, 'projects/analyze', data, config)
        assert response.status_code == 500
        assert response.json()['error']['code'] == 'analysis_failed'
        assert 'SECRET' not in response.text
    assert all(not p.exists() for p in locations)


def test_two_module_uploads_do_not_share_state():
    def run(name):
        data = archive({f'{name}.py': 'x=1', 'client.py': f'import {name}'})
        with TestClient(app) as client:
            return request(client, 'projects/analyze', data, {'change_domain': 'module', 'change_type': 'remove_module', 'target_module_id': name}).json()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, ['alpha', 'beta']))
    assert results[0]['change']['target_module_id'] == 'alpha'
    assert results[1]['change']['target_module_id'] == 'beta'
    assert results[0]['project_fingerprint'] != results[1]['project_fingerprint']


def test_explicit_function_domain_preserves_old_response():
    data = archive({'utils.py': 'def f(a): pass', 'report.py': 'from utils import f\ndef report(): f(1)'})
    config = {'target_symbol_id': 'utils.f', 'added_parameter': {'name': 'b', 'kind': 'positional_or_keyword'}}
    with TestClient(app) as client:
        old = request(client, 'projects/analyze', data, config)
        explicit = request(client, 'projects/analyze', data, {**config, 'change_domain': 'function'})
        duplicate = request(client, 'changes/validate', data, '{"change_domain":"module","change_domain":"function"}')
    assert old.status_code == explicit.status_code == 200
    assert old.json() == explicit.json()
    assert duplicate.status_code == 422
