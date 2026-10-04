"""Orchestration for Module changes; function pipeline remains independent."""

from dataclasses import dataclass

from openimpact.analysis.import_resolver import resolve_imports
from openimpact.analysis.module_change import ModuleChangeSpec, validate_module_change, project_module_layout
from openimpact.analysis.module_facts import ModuleInventory
from openimpact.analysis.module_graph import ModuleDependencyGraph
from openimpact.analysis.module_impact import (
    DirectImportImpact, ImportAssessment, IndirectModuleImpact, assess_module_imports, propagate_module_impact,
)
from openimpact.analysis.symbol_index import SymbolIndex


@dataclass(frozen=True)
class ModuleAnalysisRun:
    index: SymbolIndex
    inventory: ModuleInventory
    change_spec: ModuleChangeSpec
    graph: ModuleDependencyGraph
    assessments: tuple[ImportAssessment, ...]
    direct: tuple[DirectImportImpact, ...]
    indirect: tuple[IndirectModuleImpact, ...]


def analyze_module_project(index: SymbolIndex, spec: ModuleChangeSpec, inventory: ModuleInventory | None = None):
    inventory = inventory or ModuleInventory.from_index(index)
    validate_module_change(inventory, spec)
    surviving_files = {descriptor.file for _, descriptor in project_module_layout(inventory, spec).modules}
    graph = ModuleDependencyGraph.from_imports(tuple(reference for reference in resolve_imports(index, inventory)
                                                    if reference.file in surviving_files))
    assessments, direct = assess_module_imports(index, inventory, spec)
    indirect = propagate_module_impact(graph, direct)
    return ModuleAnalysisRun(index, inventory, spec, graph, assessments, direct, indirect)
