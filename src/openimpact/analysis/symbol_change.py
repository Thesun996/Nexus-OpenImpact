"""Immutable variable operations and virtual definitions; no source writes."""

from dataclasses import asdict, dataclass, replace
from typing import Literal
from openimpact.analysis.variable_symbols import VariableSymbol, VariableInventory, symbol_name_problem


class SymbolChangeError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class RenameModuleSymbolOperation:
    new_symbol_name: str
    change_type: Literal['rename_module_symbol'] = 'rename_module_symbol'

    def __post_init__(self):
        if self.change_type != 'rename_module_symbol':
            raise SymbolChangeError('invalid_operation', '符号重命名操作类型无效。')
        if problem := symbol_name_problem(self.new_symbol_name):
            raise SymbolChangeError(problem, '新名称必须是规范的公开 Python 标识符。')


@dataclass(frozen=True)
class RemoveModuleSymbolOperation:
    change_type: Literal['remove_module_symbol'] = 'remove_module_symbol'

    def __post_init__(self):
        if self.change_type != 'remove_module_symbol':
            raise SymbolChangeError('invalid_operation', '符号删除操作类型无效。')


@dataclass(frozen=True)
class SymbolChangeSpec:
    before: VariableSymbol
    operation: RenameModuleSymbolOperation | RemoveModuleSymbolOperation
    change_domain: Literal['symbol'] = 'symbol'

    def __post_init__(self):
        if self.change_domain != 'symbol' or not isinstance(self.operation, (RenameModuleSymbolOperation, RemoveModuleSymbolOperation)):
            raise SymbolChangeError('invalid_symbol_change', '符号变更必须使用 symbol 领域操作。')

    @property
    def target_symbol_id(self): return self.before.symbol_id

    @property
    def change_type(self): return self.operation.change_type

    @property
    def after(self):
        if isinstance(self.operation, RemoveModuleSymbolOperation): return None
        name = self.operation.new_symbol_name
        annotation = f': {self.before.annotation_source}' if self.before.annotation_source else ''
        definition = f'{name}{annotation} = {self.before.value_source}'
        return replace(self.before, name=name, symbol_id=f'{self.before.module_id}.{name}', definition=definition)

    def to_dict(self, **_kwargs):
        return {'change_domain': 'symbol', 'change_type': self.change_type,
                'target_symbol_id': self.target_symbol_id, 'target_module_id': self.before.module_id,
                'operation': asdict(self.operation), 'before': asdict(self.before),
                'after': asdict(self.after) if self.after else None,
                'analysis_scope': 'project_root_static_symbols', 'modifies_source': False}


def validate_symbol_change(inventory, spec):
    target = inventory.get(spec.target_symbol_id)
    if target is None: raise SymbolChangeError('symbol_not_found', '项目中没有唯一的目标变量或常量。')
    if not target.selectable: raise SymbolChangeError(target.reason or 'unsupported_symbol', '目标定义不属于当前支持的简单公开模块级符号。')
    if target != spec.before: raise SymbolChangeError('symbol_snapshot_mismatch', '目标符号源码快照已变化。')
    if isinstance(spec.operation, RenameModuleSymbolOperation):
        name = spec.operation.new_symbol_name
        if name == target.name: raise SymbolChangeError('unchanged_symbol_name', '新旧符号名称必须不同。')
        if name in inventory.names(target.module_id):
            raise SymbolChangeError('symbol_name_conflict', '新符号名与模块中已有绑定冲突。')


def build_symbol_change(inventory, config):
    kind = config.get('change_type') if isinstance(config, dict) else None
    keys = {'change_domain', 'change_type', 'target_symbol_id'}
    if kind == 'rename_module_symbol': keys.add('new_symbol_name')
    elif kind != 'remove_module_symbol': raise SymbolChangeError('unsupported_symbol_change', '仅支持公开模块级变量/常量的重命名与删除。')
    if config.get('change_domain') != 'symbol' or set(config) != keys or not isinstance(config['target_symbol_id'], str):
        raise SymbolChangeError('invalid_symbol_change', '符号配置缺失字段或包含不支持的字段。')
    target = inventory.get(config['target_symbol_id'])
    if target is None: raise SymbolChangeError('symbol_not_found', '项目中没有唯一的目标变量或常量。')
    operation = RenameModuleSymbolOperation(config['new_symbol_name']) if kind == 'rename_module_symbol' else RemoveModuleSymbolOperation()
    spec = SymbolChangeSpec(target, operation)
    validate_symbol_change(inventory, spec)
    return spec


def project_symbol_inventory(inventory, spec):
    validate_symbol_change(inventory, spec)
    items = tuple(item for item in inventory.symbols if item.symbol_id != spec.target_symbol_id)
    return replace(inventory, symbols=(*items, spec.after) if spec.after else items)
