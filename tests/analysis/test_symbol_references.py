from pathlib import Path
import pytest
from openimpact.analysis.symbol_index import SymbolIndex
from openimpact.analysis.variable_symbols import VariableInventory
from openimpact.analysis.symbol_references import resolve_symbol_references, symbol_dependency_graph
from openimpact.analysis.symbol_change import build_symbol_change, project_symbol_inventory


def project(tmp_path, files):
    for name, source in files.items(): (tmp_path/name).write_text(source,encoding='utf-8')
    index=SymbolIndex(tmp_path).build()
    return index, VariableInventory.from_index(index)


@pytest.mark.parametrize('source,kind,count',[
 ('from config import MAX_RETRIES','from_import',1),
 ('from config import MAX_RETRIES as RETRIES\nprint(RETRIES)','name_read',2),
 ('import config\nprint(config.MAX_RETRIES)','attribute_read',1),
 ('import config as cfg\ndef run():\n return cfg.MAX_RETRIES','attribute_read',1),
])
def test_explicit_binding_and_aliases(tmp_path,source,kind,count):
    index, data=project(tmp_path,{'config.py':'MAX_RETRIES=3','consumer.py':source})
    references=[r for r in resolve_symbol_references(index,data) if r.target_symbol_id=='config.MAX_RETRIES']
    assert len(references)==count and any(r.reference_kind==kind for r in references)
    assert all(r.status=='resolved_project' and r.file=='consumer.py' for r in references)
    graph=symbol_dependency_graph(index,data)
    assert [(e.importer_module_id,e.target_module_id) for e in graph.edges]==[('consumer','config')]
    assert all(r.reference_id.startswith('symbol-ref:') and r.expression for r in references)


@pytest.mark.parametrize('body',[
 'def run(MAX_RETRIES): return MAX_RETRIES',
 'def run():\n MAX_RETRIES=5\n return MAX_RETRIES',
 'def run():\n print(MAX_RETRIES)\n MAX_RETRIES=5',
 'def run():\n try: pass\n except Exception as MAX_RETRIES: print(MAX_RETRIES)',
 'def run(value):\n match value:\n  case MAX_RETRIES: return MAX_RETRIES',
])
def test_locals_never_match_module_variable(tmp_path,body):
    index,data=project(tmp_path,{'config.py':'MAX_RETRIES=3\n'+body})
    assert not [r for r in resolve_symbol_references(index,data) if r.target_symbol_id=='config.MAX_RETRIES']


def test_shadowed_module_alias_and_unrelated_same_name(tmp_path):
    index,data=project(tmp_path,{'config.py':'MAX_RETRIES=3','other.py':'MAX_RETRIES=9\nprint(MAX_RETRIES)',
                              'consumer.py':'import config as cfg\ndef run(cfg): return cfg.MAX_RETRIES'})
    refs=resolve_symbol_references(index,data)
    assert not [r for r in refs if r.target_symbol_id=='config.MAX_RETRIES']
    assert [r for r in refs if r.target_symbol_id=='other.MAX_RETRIES']


def test_internal_global_load_and_preexisting_read(tmp_path):
    index,data=project(tmp_path,{'config.py':'print(MAX_RETRIES)\nMAX_RETRIES=3\ndef run(): return MAX_RETRIES'})
    refs=[r for r in resolve_symbol_references(index,data) if r.reference_kind=='name_read' and r.expression=='MAX_RETRIES']
    assert [(r.line,r.status) for r in refs]==[(1,'unresolved'),(3,'resolved_project')]
    spec=build_symbol_change(data,{'change_domain':'symbol','change_type':'remove_module_symbol','target_symbol_id':'config.MAX_RETRIES'})
    after=resolve_symbol_references(index,project_symbol_inventory(data,spec))
    assert all(r.status=='unresolved' for r in after if r.expression=='MAX_RETRIES')


@pytest.mark.parametrize('source',[
 'import config as cfg\ncfg=object()\nprint(cfg.MAX_RETRIES)',
 'import config\nprint(getattr(config,"MAX_RETRIES"))',
 'from config import *\nprint(MAX_RETRIES)',
 'from .config import MAX_RETRIES',
 'from config import MAX_RETRIES\ndef outer():\n def inner(): return MAX_RETRIES\n return inner()',
])
def test_uncertain_references_not_upgraded(tmp_path,source):
    index,data=project(tmp_path,{'config.py':'MAX_RETRIES=3','consumer.py':source})
    refs=resolve_symbol_references(index,data)
    assert any(r.status=='manual_review' for r in refs) or index.parsed_files[Path('consumer.py')].symbol_diagnostics
    assert not [r for r in refs if r.reference_kind!='from_import' and r.status=='resolved_project']


def test_attribute_write_blocks_other_reads(tmp_path):
    index,data=project(tmp_path,{'config.py':'MAX_RETRIES=3','consumer.py':'import config\nconfig.MAX_RETRIES=5\nprint(config.MAX_RETRIES)'})
    refs=[r for r in resolve_symbol_references(index,data) if r.target_symbol_id=='config.MAX_RETRIES']
    assert len(refs)==2 and all(r.status=='manual_review' for r in refs)


def test_conditional_definition_is_disabled_not_silently_missing(tmp_path):
    index,data=project(tmp_path,{'config.py':'if True:\n MAX_RETRIES=3'})
    assert data.get('config.MAX_RETRIES').reason=='conditional_definition_unsupported'


def test_external_and_dynamic_exports(tmp_path):
    index,data=project(tmp_path,{'config.py':'MAX_RETRIES=3\ndef __getattr__(name): return 1','consumer.py':'from config import MAX_RETRIES\nfrom external import MAX_RETRIES as EXT'})
    refs=resolve_symbol_references(index,data)
    assert refs[0].status=='manual_review' and refs[1].status=='unresolved'


def test_mapping_rest_is_a_local_binding_not_the_imported_symbol(tmp_path):
    index, data = project(tmp_path, {'config.py':'MAX_RETRIES=3',
        'consumer.py':'from config import MAX_RETRIES\ndef f(value):\n match value:\n  case {**MAX_RETRIES}: return MAX_RETRIES\n'})
    references = [r for r in resolve_symbol_references(index, data) if r.reference_kind == 'name_read' and r.expression == 'MAX_RETRIES']
    assert len(references) == 1 and references[0].status == 'local'


@pytest.mark.parametrize('annotation', ['MAX_RETRIES', 'config.MAX_RETRIES'])
def test_annotation_root_reference_is_retained_as_manual_review(tmp_path, annotation):
    source = 'MAX_RETRIES=3\nimport config\ndef f(value: '+annotation+'): return value\n'
    index, data = project(tmp_path, {'config.py':source})
    references = [r for r in resolve_symbol_references(index, data) if r.expression == annotation]
    assert len(references) == 1
    assert references[0].status == 'manual_review' and references[0].scope == 'unsupported_scope'
