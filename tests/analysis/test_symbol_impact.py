import pytest
from openimpact.analysis.symbol_index import SymbolIndex
from openimpact.analysis.variable_symbols import VariableInventory
from openimpact.analysis.symbol_change import build_symbol_change
from openimpact.analysis.symbol_impact import analyze_symbol_project, propagate_symbol_impact
from openimpact.analysis.symbol_report import build_symbol_report


def analyze(tmp_path, sources, kind='rename_module_symbol'):
    for file, text in sources.items():
        path = tmp_path/file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    index = SymbolIndex(tmp_path).build()
    inventory = VariableInventory.from_index(index)
    config = {'change_domain': 'symbol', 'change_type': kind, 'target_symbol_id': 'config.MAX_RETRIES'}
    if kind == 'rename_module_symbol': config['new_symbol_name'] = 'RETRY_LIMIT'
    run = analyze_symbol_project(index, build_symbol_change(inventory, config), inventory)
    return run, build_symbol_report(run)


@pytest.mark.parametrize('kind', ['rename_module_symbol', 'remove_module_symbol'])
@pytest.mark.parametrize('reference', ['from config import MAX_RETRIES', 'from config import MAX_RETRIES as limit', 'import config\nx = config.MAX_RETRIES', 'import config as cfg\nx = cfg.MAX_RETRIES'])
def test_real_reference_break_and_evidence(tmp_path, kind, reference):
    run, report = analyze(tmp_path, {'config.py': 'MAX_RETRIES = 3\n', 'client.py': reference+'\n'}, kind)
    assert len(run.direct) == 1
    assert report['schema_version'] == 1 and report['report_kind'] == 'symbol_impact'
    assert 'direct_impacts' not in report and 'before_signature' not in report['change']
    item = report['reference_impacts'][0]
    assert item['before_resolution']['status'] == 'resolved_project' and item['after_resolution']['status'] == 'unresolved'
    evidence = report['evidences'][0]
    assert evidence['status'] == 'available' and evidence['source_snippet'] and evidence['source_hash']
    assert evidence['location']['file'] == 'client.py' and evidence['evidence_reference'] == item['finding_id']
    assert report['explanations'][0]['evidence_reference'] == item['finding_id']
    assert report['explanations'][0]['explanation']['risk_level'] == 'unknown'
    assert (tmp_path/'config.py').read_text() == 'MAX_RETRIES = 3\n'


def test_indirect_cycle_dedup_multiple_seeds_depth(tmp_path):
    run, report = analyze(tmp_path, {'config.py': 'MAX_RETRIES = 3\n',
        'client.py': 'import config\nx = config.MAX_RETRIES\ny = config.MAX_RETRIES\nimport dashboard\n',
        'dashboard.py': 'import client\n', 'page.py': 'import dashboard\nimport client\n', 'outer.py': 'import page\n', 'beyond.py': 'import outer\n'})
    assert len(run.direct) == 2
    assert {item.impacted_module_id: item.hop for item in run.indirect} == {'dashboard':1, 'page':1, 'outer':2}
    assert all(len(item.sources) == 2 for item in run.indirect)
    for finding in report['symbol_indirect_impacts']:
        for path in finding['propagation_path']:
            assert path['modules'][-1] == 'client'
            assert path['terminal_reference']['target_symbol_id'] == 'config.MAX_RETRIES'
            assert len(path['import_sites']) == len(path['modules']) - 1
    with pytest.raises(ValueError): propagate_symbol_impact(None, (), 3)


@pytest.mark.parametrize('text', ['def f(MAX_RETRIES):\n return MAX_RETRIES\n', 'MAX_RETRIES = 5\nprint(MAX_RETRIES)\n', 'import config\nconfig.MAX_RETRIES = 10\nprint(config.MAX_RETRIES)\n'])
def test_no_false_seed_from_shadow_or_write(tmp_path, text):
    run, _ = analyze(tmp_path, {'config.py':'MAX_RETRIES = 3\n', 'client.py':text})
    assert not run.direct and not run.indirect


def test_existing_unresolved_and_manual_do_not_propagate(tmp_path):
    run, report = analyze(tmp_path, {'config.py':'MAX_RETRIES = 3\n', 'client.py':'import config\ndef f():\n return getattr(config, "MAX_RETRIES")\n', 'page.py':'import client\n', 'missing.py':'from external import MAX_RETRIES\n'})
    assert not run.direct and not run.indirect
    assert report['coverage']['status'] == 'partial'
    assert report['summary']['unresolved_reference_count'] > 0


def test_same_module_global_read_and_annotations(tmp_path):
    run, report = analyze(tmp_path, {'config.py':'MAX_RETRIES: int = 3\ndef f():\n return MAX_RETRIES\n'})
    assert len(run.direct) == 1 and report['coverage']['status'] == 'complete'
    assert run.change_spec.after.definition == 'RETRY_LIMIT: int = 3'


def test_source_missing_degrades_report_not_analysis(tmp_path):
    run, report = analyze(tmp_path, {'config.py':'MAX_RETRIES = 3\n', 'client.py':'from config import MAX_RETRIES\n'})
    (tmp_path/'client.py').unlink()
    report = build_symbol_report(run)
    assert report['summary']['direct_reference_count'] == 1
    assert report['evidences'][0]['status'] == 'unavailable'


def test_partial_source_keeps_confirmed_evidence(tmp_path):
    _, report = analyze(tmp_path, {'config.py':'MAX_RETRIES = 3\n', 'client.py':'from config import MAX_RETRIES\n', 'bad.py':'def broken(:\n'})
    assert report['summary']['direct_reference_count'] == 1 and report['coverage']['status'] == 'partial'
    assert report['diagnostics']['parse_errors'][0]['file'] == 'bad.py'


@pytest.mark.parametrize('text', ['import external\n', 'import importlib\nimportlib.import_module("config")\n', 'if True:\n import config\n'])
def test_unused_or_dynamic_import_boundaries_are_not_silently_complete(tmp_path, text):
    run, report = analyze(tmp_path, {'config.py':'MAX_RETRIES = 3\n', 'client.py':text})
    assert not run.direct and report['coverage']['status'] == 'partial'
    assert any(report['diagnostics'][key] for key in ('unresolved_imports','manual_review_imports','import_syntax_diagnostics'))


@pytest.mark.parametrize('expression', ['setattr(config, "MAX_RETRIES", 9)', 'delattr(config, "MAX_RETRIES")', 'vars(config)["MAX_RETRIES"] = 9', 'exec("pass", config.__dict__)'])
def test_dynamic_write_elsewhere_cannot_recreate_old_name_as_a_false_direct(tmp_path, expression):
    run, report = analyze(tmp_path, {'config.py':'MAX_RETRIES = 3\n', 'client.py':'from config import MAX_RETRIES\n', 'writer.py':f'import config\n{expression}\n'})
    assert not run.direct and not run.indirect
    assert report['coverage']['status'] == 'partial'
    assert any(ref['reason'] == 'project_dynamic_write_unsupported' for ref in report['diagnostics']['manual_review_references'])


@pytest.mark.parametrize('write', [
    'import builtins as b\nb.setattr(config, "MAX_RETRIES", 9)',
    'from builtins import setattr as put\nput(config, "MAX_RETRIES", 9)',
    'import builtins as b\nb.vars(config)["MAX_RETRIES"] = 9',
])
def test_builtin_alias_dynamic_write_cannot_become_a_definite_seed(tmp_path, write):
    run, report = analyze(tmp_path, {'config.py':'MAX_RETRIES=3\n',
        'client.py':'from config import MAX_RETRIES\n', 'writer.py':'import config\n'+write+'\n', 'page.py':'import client\n'})
    assert not run.direct and not run.indirect
    assert report['coverage']['status'] == 'partial'
    assert any(ref['reason'] == 'project_dynamic_write_unsupported' for ref in report['diagnostics']['manual_review_references'])


@pytest.mark.parametrize('write', [
    'class Writer:\n config.MAX_RETRIES = 9',
    'def outer():\n def write():\n  config.MAX_RETRIES = 9\n return write',
    'config.__dict__["MAX_RETRIES"] = 9',
    'config.__dict__.update({"MAX_RETRIES": 9})',
])
def test_unsupported_scope_or_namespace_write_is_a_project_review_boundary(tmp_path, write):
    run, report = analyze(tmp_path, {'config.py':'MAX_RETRIES=3\n',
        'client.py':'from config import MAX_RETRIES\n', 'writer.py':'import config\n'+write+'\n', 'page.py':'import client\n'})
    assert not run.direct and not run.indirect
    assert report['coverage']['status'] == 'partial'
    assert any(ref['reason'] == 'project_dynamic_write_unsupported' for ref in report['diagnostics']['manual_review_references'])
