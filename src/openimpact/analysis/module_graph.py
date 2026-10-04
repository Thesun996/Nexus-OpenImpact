"""Module import edges, separate from function call edges."""

from dataclasses import dataclass

from openimpact.analysis.import_resolver import ResolvedImport


@dataclass(frozen=True)
class ModuleEdge:
    importer_module_id: str
    target_module_id: str
    reference: ResolvedImport


@dataclass(frozen=True)
class ModuleDependencyGraph:
    edges: tuple[ModuleEdge, ...]

    @classmethod
    def from_imports(cls, references: tuple[ResolvedImport, ...]):
        edges = {reference.reference_id: ModuleEdge(reference.source_module, reference.target_module_id, reference)
                 for reference in references if reference.status == "resolved_project" and reference.target_module_id is not None}
        return cls(tuple(edges[key] for key in sorted(edges)))

    def reverse(self) -> dict[str, tuple[ModuleEdge, ...]]:
        result: dict[str, list[ModuleEdge]] = {}
        for edge in self.edges:
            result.setdefault(edge.target_module_id, []).append(edge)
        return {key: tuple(sorted(edges, key=lambda edge: (edge.reference.file, edge.reference.syntax.line, edge.reference.reference_id)))
                for key, edges in result.items()}
