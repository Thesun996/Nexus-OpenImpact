"""Resolve each declared import independently within the explicit flat-root scope."""

import hashlib
from dataclasses import dataclass

from openimpact.analysis.models import ModuleImportSyntax
from openimpact.analysis.module_change import VirtualModuleLayout
from openimpact.analysis.module_facts import ModuleInventory
from openimpact.analysis.symbol_index import SymbolIndex


@dataclass(frozen=True)
class ResolvedImport:
    reference_id: str
    source_module: str
    file: str
    syntax: ModuleImportSyntax
    status: str
    target_module_id: str | None
    reason: str


def resolve_imports(index: SymbolIndex, inventory: ModuleInventory,
                    layout: VirtualModuleLayout | None = None) -> tuple[ResolvedImport, ...]:
    references = []
    for path, parsed in sorted(index.parsed_files.items()):
        source_module = index.module_name(path)
        source = inventory.get(source_module)
        for syntax in parsed.module_imports:
            identity = f"{path.as_posix()}:{syntax.statement_ordinal}:{syntax.alias_ordinal}"
            reference_id = "import:" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
            status, target, reason = _resolve_one(index, inventory, layout, source, syntax)
            references.append(ResolvedImport(reference_id, source_module, path.as_posix(), syntax, status, target, reason))
    return tuple(references)


def _resolve_one(index, inventory, layout, source, syntax):
    if source is None or not source.selectable:
        return "manual_review", None, "unsupported_importer"
    if layout is not None and not any(descriptor.file == source.file for _, descriptor in layout.modules):
        return "not_applicable", None, "importer_removed"
    if syntax.scope != "top_level":
        return "manual_review", None, "conditional_or_local_import_unsupported"
    if syntax.level:
        return "manual_review", None, "relative_import_unsupported"
    if not syntax.module or "." in syntax.module:
        return "manual_review", None, "package_import_unsupported"
    if syntax.imported_name == "*":
        return "manual_review", None, "wildcard_import_unsupported"
    target = layout.get(syntax.module) if layout else inventory.get(syntax.module)
    if target is None:
        if syntax.module in index.ambiguous_modules:
            return "unresolved", None, "ambiguous_project_module"
        return "unresolved", None, "module_not_in_project"
    if not target.selectable:
        return "manual_review", None, target.reason or "unsupported_target_module"
    if syntax.import_type == "from_import":
        symbol_id = f"{target.module_id}.{syntax.imported_name}"
        symbol = index.symbols.get(symbol_id)
        parsed = index.parsed_modules.get(target.module_id)
        if symbol is None or parsed is None or syntax.imported_name in parsed.module_rebindings:
            return "manual_review", None, "imported_member_not_proven"
    return "resolved_project", syntax.module, "unique_project_root_module"
