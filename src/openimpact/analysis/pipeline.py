"""Run the existing project analysis stages in order."""

from dataclasses import dataclass
from pathlib import Path

from openimpact.analysis.call_graph import CallGraph
from openimpact.analysis.change_spec import ChangeSpec
from openimpact.analysis.direct_impact import DirectImpactResult, analyze_direct_impact
from openimpact.analysis.indirect_impact import (
    IndirectImpactResult,
    propagate_indirect_impact,
)
from openimpact.analysis.symbol_index import SymbolIndex


@dataclass(frozen=True)
class AnalysisRun:
    project_path: Path
    change_spec: ChangeSpec
    index: SymbolIndex
    graph: CallGraph
    direct: DirectImpactResult
    indirect: IndirectImpactResult


def analyze_project(project_path: str | Path, change_spec: ChangeSpec, *, analysis_root: str = ".") -> AnalysisRun:
    """Index, resolve, validate, assess, and propagate without modifying source."""
    index = SymbolIndex(project_path, analysis_root=analysis_root).build()
    graph = CallGraph(index).build()
    direct = analyze_direct_impact(graph, change_spec)
    indirect = propagate_indirect_impact(graph, direct)
    return AnalysisRun(index.scanner.project_path, change_spec, index, graph, direct, indirect)
