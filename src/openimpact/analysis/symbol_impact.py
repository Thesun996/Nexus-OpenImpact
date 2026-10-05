"""Before/after static variable references and bounded upstream module review."""

import hashlib
import json
from collections import deque
from dataclasses import dataclass

from openimpact.analysis.symbol_change import project_symbol_inventory
from openimpact.analysis.symbol_references import resolve_symbol_references, symbol_dependency_graph


@dataclass(frozen=True)
class SymbolAssessment:
    before: object
    after: object
    effect: str
    reason: str


@dataclass(frozen=True)
class DirectSymbolImpact:
    finding_id: str
    assessment: SymbolAssessment
    rule: str
    impact_type: str = 'direct_symbol_reference'


@dataclass(frozen=True)
class SymbolPropagation:
    source_direct_impact: str
    path: tuple


@dataclass(frozen=True)
class IndirectSymbolImpact:
    finding_id: str
    impacted_module_id: str
    hop: int
    sources: tuple[SymbolPropagation, ...]
    reason: str = '此模块位于确定符号引用断裂的上游静态依赖路径中，需要检查；不保证运行时执行或失败。'

    @property
    def impact_type(self): return f'indirect_{self.hop}hop'


@dataclass(frozen=True)
class SymbolAnalysisRun:
    index: object
    inventory: object
    change_spec: object
    assessments: tuple[SymbolAssessment, ...]
    direct: tuple[DirectSymbolImpact, ...]
    indirect: tuple[IndirectSymbolImpact, ...]


def analyze_symbol_project(index, spec, inventory):
    after_inventory = project_symbol_inventory(inventory, spec)
    before = resolve_symbol_references(index, inventory)
    after = {ref.reference_id: ref for ref in resolve_symbol_references(index, after_inventory)}
    digest = hashlib.sha256(json.dumps(spec.to_dict(), sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]
    rule = 'module_symbol_renamed_breaks_reference' if spec.change_type == 'rename_module_symbol' else 'module_symbol_removed_breaks_reference'
    assessments, direct = [], []
    for old in before:
        new = after[old.reference_id]
        if old.status == 'resolved_project' and old.target_symbol_id == spec.target_symbol_id and new.status == 'unresolved' and new.reason == 'symbol_not_in_project':
            effect = 'direct_symbol_impact'
            plan = f'重命名为 {spec.after.name}' if spec.after else '删除'
            reason = f'引用原来唯一绑定 {spec.target_symbol_id}；拟{plan}后，旧名称不再提供该项目定义，产生新的静态引用断裂。此结论不保证运行时失败。'
        elif 'manual_review' in (old.status, new.status):
            effect, reason = 'manual_review', f'静态证据不足：{old.reason} / {new.reason}，需要人工检查。'
        elif old.status == 'unresolved':
            effect = 'resolution_improved' if new.status == 'resolved_project' else 'unresolved'
            reason = '修改前已无法确定项目符号，不计为本次新增影响。'
        else:
            effect, reason = 'no_impact', '没有新增的确定项目符号引用断裂。'
        assessment = SymbolAssessment(old, new, effect, reason)
        assessments.append(assessment)
        if effect == 'direct_symbol_impact':
            direct.append(DirectSymbolImpact(f'symbol-direct:{digest}:{old.reference_id}', assessment, rule))
    graph = symbol_dependency_graph(index, inventory)
    indirect = propagate_symbol_impact(graph, tuple(direct))
    return SymbolAnalysisRun(index, inventory, spec, tuple(assessments), tuple(direct), indirect)


def propagate_symbol_impact(graph, seeds, max_depth=2):
    if isinstance(max_depth, bool) or not isinstance(max_depth, int) or not 0 <= max_depth <= 2:
        raise ValueError('符号传播深度必须为 0、1 或 2。')
    reverse = graph.reverse()
    direct_modules = {seed.assessment.before.source_module for seed in seeds if seed.assessment.effect == 'direct_symbol_impact'}
    sources = {}
    for seed in seeds:
        if seed.assessment.effect != 'direct_symbol_impact': continue
        source = seed.assessment.before.source_module
        visited = {source}
        queue = deque([(source, ())])
        while queue:
            current, path = queue.popleft()
            if len(path) >= max_depth: continue
            for edge in reverse.get(current, ()):
                upstream = edge.importer_module_id
                if upstream in visited: continue
                visited.add(upstream)
                next_path = (edge, *path)
                if upstream not in direct_modules:
                    sources.setdefault(upstream, []).append(SymbolPropagation(seed.finding_id, next_path))
                queue.append((upstream, next_path))
    return tuple(IndirectSymbolImpact(f'symbol-indirect:{module}', module,
                 min(len(source.path) for source in paths), tuple(paths)) for module, paths in sorted(sources.items()))
