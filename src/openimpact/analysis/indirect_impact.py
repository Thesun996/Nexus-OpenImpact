"""Propagate definite direct impacts two caller levels up a resolved call graph."""

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Literal

from openimpact.analysis.call_graph import CallEdge, CallGraph
from openimpact.analysis.direct_impact import DirectImpactResult, ImpactFinding


@dataclass(frozen=True)
class PropagationEvidence:
    """A forward caller-to-callee path ending at the original direct call site."""

    source_direct_impact: ImpactFinding
    propagation_path: tuple[CallEdge, ...]


@dataclass(frozen=True)
class IndirectImpactFinding:
    impacted_symbol_id: str
    impact_type: Literal["indirect_1hop", "indirect_2hop"]
    graph_distance: Literal[2, 3]
    certainty: Literal["needs_review"]
    reason: str
    sources: tuple[PropagationEvidence, ...]


@dataclass(frozen=True)
class IndirectImpactResult:
    findings: tuple[IndirectImpactFinding, ...]


def _edge_key(edge: CallEdge) -> tuple[str, str, str, int, int]:
    return (
        edge.caller_symbol_id, edge.callee_symbol_id, edge.file.as_posix(),
        edge.line, edge.col_offset,
    )


def _direct_edge(graph: CallGraph, finding: ImpactFinding) -> CallEdge:
    call = finding.assessment
    matches = [
        edge for edge in graph.edges
        if edge.caller_symbol_id == call.caller_symbol_id
        and edge.callee_symbol_id == call.target_symbol_id
        and edge.file == call.file
        and edge.line == call.line
        and edge.col_offset == call.col_offset
        and edge.status == "resolved"
    ]
    if len(matches) != 1:
        raise ValueError("Direct Impact 缺少唯一的原始调用边；请使用同一索引重新分析。")
    return matches[0]


def propagate_indirect_impact(
    graph: CallGraph, direct: DirectImpactResult, max_depth: int = 2
) -> IndirectImpactResult:
    """Return one finding per upstream symbol, with one shortest path per direct seed."""
    if not isinstance(max_depth, int) or isinstance(max_depth, bool) or not 0 <= max_depth <= 2:
        raise ValueError("V1 的 max_depth 必须是 0、1 或 2。")
    if not direct.validation.valid or max_depth == 0:
        return IndirectImpactResult(())

    reverse: dict[str, list[CallEdge]] = defaultdict(list)
    for edge in graph.edges:
        if edge.status == "resolved":
            reverse[edge.callee_symbol_id].append(edge)
    for edges in reverse.values():
        edges.sort(key=_edge_key)

    seeds = sorted(
        (finding for finding in direct.findings if finding.effect == "direct_impact"),
        key=lambda finding: (
            finding.assessment.file.as_posix(), finding.assessment.line,
            finding.assessment.col_offset, finding.assessment.caller_symbol_id,
        ),
    )
    direct_callers = {finding.assessment.caller_symbol_id for finding in seeds}
    evidence_by_symbol: dict[str, list[PropagationEvidence]] = defaultdict(list)

    for seed in seeds:
        caller = seed.assessment.caller_symbol_id
        direct_edge = _direct_edge(graph, seed)
        # A breadth-first walk selects a shortest representative path per seed and symbol.
        queue = deque([(caller, (direct_edge,), 0)])
        visited = {caller}
        while queue:
            current, path, depth = queue.popleft()
            if depth == max_depth:
                continue
            for edge in reverse[current]:
                upstream = edge.caller_symbol_id
                if upstream in visited:
                    continue
                visited.add(upstream)
                new_path = (edge, *path)
                new_depth = depth + 1
                if upstream not in direct_callers:
                    evidence_by_symbol[upstream].append(PropagationEvidence(seed, new_path))
                queue.append((upstream, new_path, new_depth))

    findings: list[IndirectImpactFinding] = []
    for symbol_id, sources in sorted(evidence_by_symbol.items()):
        min_depth = min(len(source.propagation_path) - 1 for source in sources)
        impact_type = "indirect_1hop" if min_depth == 1 else "indirect_2hop"
        findings.append(IndirectImpactFinding(
            symbol_id, impact_type, min_depth + 1, "needs_review",
            "该符号位于确定 Direct Impact 的上游调用路径中，建议检查；静态路径不保证运行时失败。",
            tuple(sources),
        ))
    return IndirectImpactResult(tuple(findings))
