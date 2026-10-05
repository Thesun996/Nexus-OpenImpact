import hashlib
from dataclasses import FrozenInstanceError
import pytest
from openimpact.analysis.symbol_index import SymbolIndex
from openimpact.analysis.variable_symbols import VariableInventory
from openimpact.analysis.symbol_change import build_symbol_change, SymbolChangeError, project_symbol_inventory


def inventory(tmp_path, source='MAX_RETRIES = 3\n'):
    (tmp_path/'config.py').write_text(source, encoding='utf-8')
    return VariableInventory.from_index(SymbolIndex(tmp_path).build())


def config(kind='rename_module_symbol', new='RETRY_LIMIT', target='config.MAX_RETRIES'):
    data = {'change_domain':'symbol','change_type':kind,'target_symbol_id':target}
    if kind == 'rename_module_symbol': data['new_symbol_name'] = new
    return data


@pytest.mark.parametrize('source', ['MAX_RETRIES = 3', 'MAX_RETRIES: int = 3', 'MAX_RETRIES = None', 'MAX_RETRIES = False', 'MAX_RETRIES = 0', 'MAX_RETRIES = ""', 'MAX_RETRIES = -3'])
def test_simple_definition_metadata(tmp_path, source):
    data = inventory(tmp_path, source)
    symbol = data.get('config.MAX_RETRIES')
    assert symbol.selectable and symbol.line == 1 and symbol.file == 'config.py'
    assert symbol.source_hash == hashlib.sha256((tmp_path/'config.py').read_bytes()).hexdigest()
    assert symbol.definition == source


@pytest.mark.parametrize('kind',['rename_module_symbol','remove_module_symbol'])
def test_projection_is_immutable_and_does_not_edit_source(tmp_path, kind):
    data = inventory(tmp_path)
    original = (tmp_path/'config.py').read_bytes()
    spec = build_symbol_change(data, config(kind))
    with pytest.raises(FrozenInstanceError): spec.change_domain = 'function'
    projected = project_symbol_inventory(data,spec)
    assert data.get('config.MAX_RETRIES') and projected.get('config.MAX_RETRIES') is None
    assert bool(projected.get('config.RETRY_LIMIT')) == (kind == 'rename_module_symbol')
    assert (tmp_path/'config.py').read_bytes() == original
    assert spec.to_dict()['modifies_source'] is False
    assert 'before_signature' not in spec.to_dict()


@pytest.mark.parametrize('new',['class','bad.name','../X','',None,42,'_hidden','ＭＡＸ','MAX_RETRIES'])
def test_invalid_names(tmp_path,new):
    with pytest.raises(SymbolChangeError): build_symbol_change(inventory(tmp_path), config(new=new))


@pytest.mark.parametrize('source',['MAX_RETRIES=1\nMAX_RETRIES=2','MAX_RETRIES=func()','MAX_RETRIES: int','MAX_RETRIES=1\ndef set_value():\n global MAX_RETRIES\n MAX_RETRIES=2','MAX_RETRIES=1\ndef __getattr__(name): return 1'])
def test_unsupported_definition_rejected(tmp_path,source):
    with pytest.raises(SymbolChangeError): build_symbol_change(inventory(tmp_path,source),config())


@pytest.mark.parametrize('binding',['RETRY_LIMIT=4','def RETRY_LIMIT(): pass','import math as RETRY_LIMIT','class RETRY_LIMIT: pass','if True:\n RETRY_LIMIT=4'])
def test_conflict_in_module_namespace(tmp_path,binding):
    with pytest.raises(SymbolChangeError) as error:
        build_symbol_change(inventory(tmp_path,'MAX_RETRIES=3\n'+binding),config())
    assert error.value.code == 'symbol_name_conflict'


def test_local_variable_not_registered_and_missing_target(tmp_path):
    data=inventory(tmp_path,'def run():\n MAX_RETRIES=5\n return MAX_RETRIES')
    assert data.symbols == ()
    with pytest.raises(SymbolChangeError): build_symbol_change(data,config())


@pytest.mark.parametrize('binding', [
    'def f(value=(MAX_RETRIES := 5)): pass',
    'class C:\n global MAX_RETRIES\n MAX_RETRIES = 5',
    'match {}:\n case {**MAX_RETRIES}: pass',
    '@(decorator := lambda f: f)\ndef f(): pass',
])
def test_executed_definition_and_pattern_bindings_are_not_missing_from_namespace(tmp_path, binding):
    data = inventory(tmp_path, 'MAX_RETRIES = 3\n' + binding + '\n')
    if binding.startswith('@'):
        with pytest.raises(SymbolChangeError) as error:
            build_symbol_change(data, config(new='decorator'))
        assert error.value.code == 'symbol_name_conflict'
    else:
        assert data.get('config.MAX_RETRIES').selectable is False
        with pytest.raises(SymbolChangeError): build_symbol_change(data, config())
