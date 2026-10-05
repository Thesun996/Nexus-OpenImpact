"""Module and symbol advice starts at the original reference, never a guessed use."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from openimpact.analysis.symbol_index import SymbolIndex
from openimpact.analysis.module_facts import ModuleInventory
from openimpact.analysis.module_change import build_module_change
from openimpact.analysis.module_pipeline import analyze_module_project
from openimpact.analysis.module_report import build_module_report
from openimpact.analysis.variable_symbols import VariableInventory
from openimpact.analysis.symbol_change import build_symbol_change
from openimpact.analysis.symbol_impact import analyze_symbol_project
from openimpact.analysis.symbol_report import build_symbol_report

EXAMPLES = Path(__file__).resolve().parents[2] / 'examples'


def run_demo(name, root=None):
    project = root or EXAMPLES / name
    config = json.loads((EXAMPLES / name / 'change.json').read_text(encoding='utf-8'))
    index = SymbolIndex(project).build()
    if config['change_domain'] == 'module':
        inventory = ModuleInventory.from_index(index)
        return analyze_module_project(index, build_module_change(inventory, config), inventory), build_module_report
    inventory = VariableInventory.from_index(index)
    return analyze_symbol_project(index, build_symbol_change(inventory, config), inventory), build_symbol_report


@pytest.mark.parametrize('name', ['module_rename', 'module_removal', 'symbol_rename', 'symbol_removal'])
def test_reference_advice_checks_terminal_before_upstream(name):
    run, builder = run_demo(name)
    report = builder(run)
    terminal = report['evidences'][0]['location']
    original = f"{terminal['file']}:{terminal['line']}:{terminal['column']}"
    text = report['explanations'][-1]['explanation']['suggested_check']
    assert original in text
    assert text.index(original) < text.index('再核对上游导入')
    assert '没有判定其运行时一定失败' in text
    assert report['explanations'][-1]['explanation']['risk_level'] == 'unknown'
    assert report['coverage']['status'] == 'complete'
    if 'rename' in name:
        assert ' → ' in report['explanations'][0]['explanation']['why_affected']
        expected = 'utils → formatting' if name == 'module_rename' else 'config.MAX_RETRIES → RETRY_LIMIT'
        assert expected in report['explanations'][0]['explanation']['why_affected']
    else:
        assert '拟删除' in report['explanations'][0]['explanation']['why_affected']


@pytest.mark.parametrize('name', ['module_rename', 'symbol_rename'])
def test_missing_terminal_source_does_not_supply_old_reference_as_current_source(name, tmp_path):
    for path in (EXAMPLES / name).glob('*.py'):
        (tmp_path / path.name).write_bytes(path.read_bytes())
    run, builder = run_demo(name, tmp_path)
    baseline = builder(run)
    terminal = baseline['evidences'][0]['location']
    (tmp_path / terminal['file']).unlink()
    report = builder(run)
    assert report['explanations'][0]['explanation'] is None
    assert '源码未能复核' in report['explanations'][-1]['explanation']['suggested_check']
    assert report['summary'] == baseline['summary']


def test_symbol_evidence_failure_does_not_generate_confident_explanation():
    run, builder = run_demo('symbol_rename')
    with patch('openimpact.analysis.symbol_report.read_source_snapshot', side_effect=OSError('missing')):
        report = builder(run)
    assert all(record['explanation'] is None and record['status'] == 'unavailable' for record in report['explanations'])
    assert report['summary']['direct_reference_count'] == 1
