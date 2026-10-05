"""Explicit lexical variable binding without evaluating imports or expressions."""

import builtins
import hashlib
from collections import Counter
from dataclasses import asdict, dataclass
from openimpact.analysis.import_resolver import ResolvedImport, resolve_imports
from openimpact.analysis.module_graph import ModuleDependencyGraph


@dataclass(frozen=True)
class SymbolReference:
    reference_id: str
    source_module: str
    file: str
    line: int
    column: int
    end_line: int
    end_column: int
    expression: str
    reference_kind: str
    scope: str
    status: str
    target_symbol_id: str | None
    reason: str

    def to_dict(self):
        data = asdict(self)
        data['location'] = {'file':self.file,'line':self.line,'column':self.column,'end_line':self.end_line,'end_column':self.end_column}
        return data


def import_bindings(parsed):
    bindings = {}
    for syntax in parsed.module_imports:
        if syntax.scope != 'top_level': continue
        name = syntax.alias or (syntax.module.split('.')[0] if syntax.import_type == 'import' else syntax.imported_name)
        if name: bindings[name] = syntax
    return bindings


def lookup(inventory, module, name):
    descriptor = inventory.modules.get(module)
    if descriptor is None: return 'unresolved', None, 'module_not_in_project'
    if not descriptor.selectable: return 'manual_review', None, descriptor.reason or 'unsupported_module'
    symbol = inventory.get(f'{module}.{name}')
    if symbol is None: return 'unresolved', None, 'symbol_not_in_project'
    if not symbol.selectable: return 'manual_review', None, symbol.reason or 'unsupported_symbol'
    return 'resolved_project', symbol.symbol_id, 'unique_public_module_symbol'


def resolve_symbol_references(index, inventory):
    results = []
    for file, parsed in sorted(index.parsed_files.items()):
        module = index.module_name(file)
        source = inventory.modules.get(module)
        binding = import_bindings(parsed)
        counts = dict(parsed.symbol_binding_counts)
        for syntax in parsed.module_imports:
            if syntax.import_type != 'from_import': continue
            if syntax.scope != 'top_level' or syntax.level or not syntax.module or '.' in syntax.module or syntax.imported_name == '*':
                status, target, reason = 'manual_review', None, 'unsupported_symbol_import'
            else:
                status, target, reason = lookup(inventory, syntax.module, syntax.imported_name)
                # A known function belongs to the original domain, not a missing variable.
                if status == 'unresolved' and f'{syntax.module}.{syntax.imported_name}' in index.symbols:
                    status, reason = 'unrelated', 'function_symbol'
            if source is None or not source.selectable: status, target, reason = 'manual_review', None, 'unsupported_importer'
            results.append(make_reference(file, module, syntax, 'from_import', status, target, reason))
        for read in parsed.symbol_reads:
            status, target, reason = resolve_read(index, inventory, module, source, parsed, binding, counts, read)
            results.append(make_reference(file, module, read, read.kind, status, target, reason))
    # Attribute stores can recreate a name in the hypothetical layout. Do not
    # classify other reads of that target as definite in this conservative release.
    mutations = {ref.target_symbol_id for ref in results if ref.reference_kind == 'attribute_write' and ref.target_symbol_id}
    if mutations:
        from dataclasses import replace
        results = [replace(ref, status='manual_review', reason='project_attribute_write_unsupported')
                   if ref.target_symbol_id in mutations else ref for ref in results]
    if any(code == 'dynamic_symbol_write' for parsed in index.parsed_files.values() for code, _, _ in parsed.symbol_diagnostics):
        from dataclasses import replace
        results = [replace(ref, status='manual_review', reason='project_dynamic_write_unsupported')
                   if ref.status == 'resolved_project' else ref for ref in results]
    return tuple(results)


def resolve_read(index, inventory, module, source, parsed, bindings, counts, read):
    root = read.path[0]
    if read.shadowed: return 'local', None, 'local_binding'
    if source is None or not source.selectable: return 'manual_review', None, 'unsupported_importer'
    if len(read.path) == 1 and root in vars(builtins) and root not in parsed.symbol_bound_names and root not in bindings:
        return 'unrelated', None, 'builtin'
    if read.scope == 'unsupported_scope': return 'manual_review', None, 'unsupported_reference_scope'
    imported = bindings.get(root)
    if imported and counts.get(root) != 1: return 'manual_review', None, 'import_binding_rebound'
    if imported and read.scope == 'module' and read.line <= imported.line:
        return 'unresolved', None, 'read_before_import'
    if imported:
        if imported.level or not imported.module or '.' in imported.module or imported.imported_name == '*':
            return 'manual_review', None, 'unsupported_symbol_import'
        if read.kind in {'attribute_read','attribute_write'}:
            if imported.import_type != 'import': return 'manual_review', None, 'object_attribute_not_proven'
            status, target, reason = lookup(inventory, imported.module, read.path[1])
        else:
            if imported.import_type == 'import': return 'unrelated', None, 'module_binding'
            status, target, reason = lookup(inventory, imported.module, imported.imported_name)
            if status == 'unresolved' and f'{imported.module}.{imported.imported_name}' in index.symbols:
                return 'unrelated', None, 'function_symbol'
    elif read.kind in {'attribute_read','attribute_write'}:
        return 'unresolved', None, 'object_module_binding_not_proven'
    else:
        status, target, reason = lookup(inventory, module, root)
        if status == 'unresolved' and (root in parsed.symbol_bound_names and not any(item.name == root and item.module_id == module for item in inventory.symbols)):
            # Functions/classes/imports are stable other bindings. A removed
            # variable retains its original syntax fact, so missing is explicit.
            if any(item.name == root for item in parsed.variable_definitions):
                return 'unresolved', None, 'symbol_not_in_project'
            return 'unrelated', None, 'other_static_binding'
        if status == 'unresolved' and root in vars(builtins): return 'unrelated', None, 'builtin'
        if status == 'resolved_project' and read.scope == 'module' and read.line <= inventory.get(target).line:
            return 'unresolved', None, 'read_before_definition'
    if read.kind == 'attribute_write' and status == 'resolved_project':
        return 'manual_review', target, 'attribute_write_unsupported'
    if status == 'resolved_project' and parsed.symbol_diagnostics:
        return 'manual_review', target, 'dynamic_or_complex_reference_in_source'
    return status, target, reason


def make_reference(file, module, node, kind, status, target, reason):
    if kind == 'from_import':
        text, scope = node.source_text, node.scope
        suffix = f':{node.statement_ordinal}:{node.alias_ordinal}'
    else:
        text, scope, suffix = node.expression, node.scope, ':' + '.'.join(node.path)
    identity = f'{file.as_posix()}:{kind}:{node.line}:{node.column}{suffix}'
    ref_id = 'symbol-ref:' + hashlib.sha256(identity.encode('utf-8')).hexdigest()[:24]
    return SymbolReference(ref_id,module,file.as_posix(),node.line,node.column,node.end_line,node.end_column,text,kind,scope,status,target,reason)


def resolve_symbol_imports(index, inventory):
    imports = []
    for ref in resolve_imports(index, inventory.modules):
        if ref.status == 'manual_review' and ref.reason == 'imported_member_not_proven':
            status, _, _ = lookup(inventory, ref.syntax.module, ref.syntax.imported_name)
            if status == 'resolved_project':
                ref = ResolvedImport(ref.reference_id, ref.source_module, ref.file, ref.syntax,
                                     'resolved_project', ref.syntax.module, 'unique_public_module_symbol')
        imports.append(ref)
    return tuple(imports)


def symbol_dependency_graph(index, inventory):
    return ModuleDependencyGraph.from_imports(resolve_symbol_imports(index, inventory))
