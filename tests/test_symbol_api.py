import hashlib
import io
import json
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from openimpact.api import app
from openimpact.repository import zip_inspector


def archive(files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as zip:
        for name, source in files.items(): zip.writestr(name, source)
    return stream.getvalue()


def submit(client, path, data, change=None, fingerprint=None):
    fields = {'change': json.dumps(change)} if change is not None else {}
    if fingerprint: fields['expected_fingerprint'] = fingerprint
    return client.post('/api/v1/'+path, data=fields, files={'file':('project.zip',data,'application/zip')})


@pytest.mark.parametrize('kind',['rename_module_symbol','remove_module_symbol'])
def test_three_steps_same_snapshot_cleanup(kind, monkeypatch):
    data = archive({'config.py':'MAX_RETRIES = 3\n', 'client.py':'import config\nlimit = config.MAX_RETRIES\n', 'dashboard.py':'import client\n', 'page.py':'import dashboard\n'})
    change = {'change_domain':'symbol','change_type':kind,'target_symbol_id':'config.MAX_RETRIES'}
    if kind == 'rename_module_symbol': change['new_symbol_name'] = 'RETRY_LIMIT'
    paths = []
    original = zip_inspector.TemporaryDirectory
    def track(*args, **kwargs):
        result = original(*args, **kwargs)
        paths.append(Path(result.name))
        return result
    monkeypatch.setattr(zip_inspector, 'TemporaryDirectory', track)
    with TestClient(app) as client:
        inspect = submit(client, 'projects/inspect', data).json()
        assert any(item['symbol_id'] == 'config.MAX_RETRIES' for item in inspect['symbol_inventory']['symbols'])
        fingerprint = inspect['project_fingerprint']
        assert fingerprint == hashlib.sha256(data).hexdigest()
        validated = submit(client, 'changes/validate', data, change, fingerprint)
        assert validated.status_code == 200, validated.text
        report = submit(client, 'projects/analyze', data, change, fingerprint)
        assert report.status_code == 200, report.text
    body = report.json()
    assert body['change'] == validated.json()['change_spec']
    assert [body['summary'][key] for key in ('direct_reference_count','indirect_1hop_module_count','indirect_2hop_module_count')] == [1,1,1]
    assert body['coverage']['status'] == 'partial' # limit = config.MAX_RETRIES is a complex, disabled definition.
    assert len(paths) == 3 and all(not path.exists() for path in paths)
    assert all(str(path) not in json.dumps(body) for path in paths)
    assert body['evidences'][2]['propagation_path'][0]['modules'] == ['page','dashboard','client']
    assert body['evidences'][2]['propagation_path'][0]['terminal_reference']['expression'] == 'config.MAX_RETRIES'
    assert all(a['evidence_reference'] == b['evidence_reference'] for a,b in zip(body['evidences'],body['explanations']))


@pytest.mark.parametrize('patch', [{'target_symbol_id':'config.MISSING'}, {'new_symbol_name':'class'}, {'new_symbol_name':'MAX_RETRIES'}, {'new_symbol_name':'other'}, {'path':'C:/secret.py'}])
def test_invalid_symbol_config(patch):
    change = {'change_domain':'symbol','change_type':'rename_module_symbol','target_symbol_id':'config.MAX_RETRIES','new_symbol_name':'RETRY_LIMIT', **patch}
    with TestClient(app) as client:
        response = submit(client,'changes/validate',archive({'config.py':'MAX_RETRIES=3\nother=2\n'}),change)
    assert response.status_code == 422 and response.json()['validation']['valid'] is False


def test_fingerprint_and_invalid_zip():
    change = {'change_domain':'symbol','change_type':'remove_module_symbol','target_symbol_id':'config.MAX_RETRIES'}
    with TestClient(app) as client:
        assert submit(client,'projects/analyze',archive({'config.py':'MAX_RETRIES=3'}),change,'a'*64).status_code == 409
        assert submit(client,'projects/analyze',b'badzip',change).status_code == 400


def test_analysis_failure_safe_and_cleanup(monkeypatch):
    import openimpact.api as api
    paths = []
    original = zip_inspector.TemporaryDirectory
    def track(*args, **kwargs):
        result = original(*args, **kwargs); paths.append(Path(result.name)); return result
    monkeypatch.setattr(zip_inspector,'TemporaryDirectory',track)
    def fail(*args): raise RuntimeError('secret C:/private token')
    monkeypatch.setattr(api,'analyze_symbol_project',fail)
    with TestClient(app) as client:
        response = submit(client,'projects/analyze',archive({'config.py':'MAX_RETRIES=3'}),{'change_domain':'symbol','change_type':'remove_module_symbol','target_symbol_id':'config.MAX_RETRIES'})
    assert response.status_code == 500 and 'secret' not in response.text
    assert all(not path.exists() for path in paths)


def test_concurrent_symbol_requests_keep_distinct_snapshots():
    def analyze(name, value):
        data = archive({'config.py':f'{name} = {value}\n', 'client.py':f'from config import {name}\n'})
        with TestClient(app) as client:
            report = submit(client,'projects/analyze',data,{'change_domain':'symbol','change_type':'remove_module_symbol','target_symbol_id':f'config.{name}'})
        assert report.status_code == 200
        body = report.json()
        assert body['project_fingerprint'] == hashlib.sha256(data).hexdigest()
        assert body['change']['before']['value_source'] == str(value)
        assert body['reference_impacts'][0]['target_symbol_id'] == f'config.{name}'
        assert body['evidences'][0]['source_snippet'] == f'from config import {name}'
        return body
    with ThreadPoolExecutor(max_workers=2) as workers:
        first = workers.submit(analyze,'MAX_RETRIES',3)
        second = workers.submit(analyze,'API_VERSION',9)
        assert first.result()['project_fingerprint'] != second.result()['project_fingerprint']
