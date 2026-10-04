"""Evidence for real import references and module dependency paths."""

from dataclasses import asdict, dataclass

from openimpact.analysis.module_graph import ModuleEdge
from openimpact.analysis.module_impact import DirectImportImpact, IndirectModuleImpact
from openimpact.reporting.source_reader import read_source_snapshot


def import_site(reference):
    syntax = reference.syntax
    return {"file": reference.file, "line": syntax.line, "column": syntax.column,
            "end_line": syntax.end_line, "end_column": syntax.end_column,
            "reference_id": reference.reference_id}


@dataclass(frozen=True)
class ImportEvidence:
    evidence_reference: str
    impact_type: str
    target_module_id: str
    location: dict | None
    source_snippet: str | None
    source_hash: str | None
    import_expression: str | None
    rule: str
    reason: str
    propagation_path: tuple[dict, ...]
    status: str
    diagnostics: tuple[dict, ...]

    def to_dict(self):
        return asdict(self)


class ImportEvidenceBuilder:
    def __init__(self, project_root, inventory):
        self.project_root = project_root
        self.inventory = inventory

    def build(self, finding: DirectImportImpact | IndirectModuleImpact):
        if isinstance(finding, DirectImportImpact):
            reference = finding.assessment.before
            paths = ((finding.finding_id, (ModuleEdge(reference.source_module, reference.target_module_id, reference),)),)
            reason, rule = finding.assessment.reason, finding.rule
        else:
            paths = tuple((source.source_direct_impact, source.path) for source in finding.sources)
            representative = min(finding.sources, key=lambda source: len(source.path))
            reference = representative.path[0].reference
            reason, rule = finding.reason, "resolved_upstream_module_path"
        descriptor = self.inventory.get(reference.source_module)
        _, snippet, digest, diagnostics = read_source_snapshot(
            self.project_root, reference.file, reference.syntax.line, reference.syntax.column,
            reference.syntax.end_line, descriptor.source_hash if descriptor else None,
        )
        evidence_paths = tuple({
            "modules": [edges[0].importer_module_id, *(edge.target_module_id for edge in edges)],
            "import_sites": [import_site(edge.reference) for edge in edges],
            "source_direct_impact": seed,
        } for seed, edges in paths)
        return ImportEvidence(
            finding.finding_id, finding.impact_type, finding.target_module_id, import_site(reference),
            snippet, digest, reference.syntax.source_text, rule, reason, evidence_paths,
            "unavailable" if diagnostics or snippet is None else "available",
            tuple(asdict(item) for item in diagnostics),
        )
