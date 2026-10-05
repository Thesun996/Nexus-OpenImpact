"""Separate public variable inventory; the frozen function SymbolIndex is unchanged."""

import keyword
import unicodedata
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

from openimpact.analysis.module_facts import ModuleInventory


def symbol_name_problem(name):
    if not isinstance(name, str) or not name.isidentifier() or keyword.iskeyword(name):
        return 'invalid_symbol_name'
    if unicodedata.normalize('NFKC', name) != name:
        return 'non_normalized_symbol_name'
    if name.startswith('_'):
        return 'private_symbol_unsupported'
    return None


@dataclass(frozen=True)
class VariableSymbol:
    symbol_id: str
    module_id: str
    name: str
    file: str
    source_hash: str
    line: int
    column: int
    end_line: int
    end_column: int
    definition: str
    value_source: str | None
    annotation_source: str | None
    kind: str
    selectable: bool
    reason: str | None


@dataclass(frozen=True)
class VariableInventory:
    symbols: tuple[VariableSymbol, ...]
    modules: ModuleInventory
    bound_names: tuple[tuple[str, tuple[str, ...]], ...]
    analysis_scope: str = 'project_root_static_symbols'

    @classmethod
    def from_index(cls, index, modules=None):
        modules = modules or ModuleInventory.from_index(index)
        values, namespace = [], []
        for module in modules.modules:
            parsed = index.parsed_files.get(Path(module.file))
            if parsed is None: continue
            namespace.append((module.module_id, tuple(sorted(parsed.symbol_bound_names))))
            grouped = defaultdict(list)
            for definition in parsed.variable_definitions:
                grouped[definition.name].append(definition)
            for name, group in sorted(grouped.items()):
                definition = group[0]
                reason = module.reason or symbol_name_problem(name) or definition.reason
                if len(group) > 1: reason = 'symbol_rebound'
                values.append(VariableSymbol(f'{module.module_id}.{name}', module.module_id, name, module.file,
                    module.source_hash, definition.line, definition.column, definition.end_line, definition.end_column,
                    definition.expression, definition.value_source, definition.annotation_source,
                    'constant' if name.isupper() else 'variable', reason is None, reason))
        return cls(tuple(values), modules, tuple(namespace))

    def get(self, symbol_id):
        found = [item for item in self.symbols if item.symbol_id == symbol_id]
        return found[0] if len(found) == 1 else None

    def names(self, module):
        return next((set(names) for owner, names in self.bound_names if owner == module), set())

    def to_dict(self):
        return {'analysis_scope': self.analysis_scope, 'symbols': [asdict(item) for item in self.symbols]}
