"""Compare virtual import bindings and propagate definite seeds at most two hops."""

import hashlib
import json
from collections import deque
from dataclasses import dataclass

from openimpact.analysis.import_resolver import ResolvedImport, resolve_imports
from openimpact.analysis.module_change import ModuleChangeSpec, RenameModuleOperation, project_module_layout
from openimpact.analysis.module_facts import ModuleInventory
from openimpact.analysis.module_graph import ModuleDependencyGraph, ModuleEdge
from openimpact.analysis.symbol_index import SymbolIndex


@dataclass(frozen=True)
class ImportAssessment:
    before: ResolvedImport
    after: ResolvedImport
    effect: str
    reason: str


@dataclass(frozen=True)
class DirectImportImpact:
    finding_id: str
    assessment: ImportAssessment
    target_module_id: str
    rule: str
    impact_type: str = "direct_import"


@dataclass(frozen=True)
class ModulePropagation:
    source_direct_impact: str
    path: tuple[ModuleEdge, ...]


@dataclass(frozen=True)
class IndirectModuleImpact:
    finding_id: str
    impacted_module_id: str
    target_module_id: str
    impact_type: str
    hop: int
    graph_distance: int
    sources: tuple[ModulePropagation, ...]
    reason: str = "此模块位于确定导入引用影响的上游静态依赖路径中，建议检查；路径不保证运行时执行或失败。"
    certainty: str = "needs_review"


def assess_module_imports(index: SymbolIndex, inventory: ModuleInventory, spec: ModuleChangeSpec):
    layout = project_module_layout(inventory, spec)
    before = resolve_imports(index, inventory)
    after = {item.reference_id: item for item in resolve_imports(index, inventory, layout)}
    assessments = []
    direct = []
    digest = hashlib.sha256(json.dumps(spec.to_dict(), sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]
    renamed = isinstance(spec.operation, RenameModuleOperation)
    rule = "module_renamed_breaks_project_import" if renamed else "module_removed_breaks_project_import"
    for old in before:
        new = after[old.reference_id]
        if new.status == "not_applicable":
            effect, reason = "source_removed", "导入来源模块本身已从虚拟布局移除，不计为存续源码的新引用断裂。"
        elif (old.status == "resolved_project" and old.target_module_id == spec.target_module_id
                and new.status == "unresolved" and new.reason == "module_not_in_project"):
            effect = "direct_import_impact"
            operation = f"重命名为 {spec.operation.new_module_name}" if renamed else "删除"
            reason = (f"此导入原来唯一绑定到项目模块 {spec.target_module_id}；拟{operation} 后，"
                      "旧项目模块名称不再提供，原导入引用发生静态断裂。此结论限定项目根静态解析，不保证运行时失败。")
        elif "manual_review" in (old.status, new.status):
            effect, reason = "manual_review", f"导入语义不在可确定范围：{old.reason} / {new.reason}。需要人工检查。"
        elif old.status == "unresolved":
            effect = "resolution_improved" if new.status == "resolved_project" else "unresolved"
            reason = "修改前未能绑定项目目标；不归为本次新增的确定影响。"
        else:
            effect, reason = "no_impact", "此导入仍绑定同一受支持的项目模块。"
        assessment = ImportAssessment(old, new, effect, reason)
        assessments.append(assessment)
        if effect == "direct_import_impact":
            direct.append(DirectImportImpact(f"module-direct:{digest}:{old.reference_id}", assessment, spec.target_module_id, rule))
    return tuple(assessments), tuple(direct)


def propagate_module_impact(graph: ModuleDependencyGraph, seeds: tuple[DirectImportImpact, ...], max_depth: int = 2):
    if isinstance(max_depth, bool) or not isinstance(max_depth, int) or not 0 <= max_depth <= 2:
        raise ValueError("模块传播深度必须为 0、1 或 2。")
    reverse = graph.reverse()
    edges = {edge.reference.reference_id: edge for edge in graph.edges}
    direct_modules = {seed.assessment.before.source_module for seed in seeds}
    sources: dict[str, list[ModulePropagation]] = {}
    target_by_module = {}
    for seed in seeds:
        if seed.assessment.effect != "direct_import_impact":
            continue
        first = edges.get(seed.assessment.before.reference_id)
        if first is None or first.reference != seed.assessment.before:
            raise ValueError("模块 Direct seed 缺少同一快照的原始确定导入边。")
        queue = deque([(first.importer_module_id, (first,), 0)])
        visited = {first.importer_module_id}
        while queue:
            current, path, depth = queue.popleft()
            if depth == max_depth:
                continue
            for edge in reverse.get(current, ()):
                upstream = edge.importer_module_id
                if upstream in visited:
                    continue
                visited.add(upstream)
                next_path = (edge, *path)
                if upstream not in direct_modules:
                    sources.setdefault(upstream, []).append(ModulePropagation(seed.finding_id, next_path))
                    target_by_module[upstream] = seed.target_module_id
                queue.append((upstream, next_path, depth + 1))
    findings = []
    for module, paths in sorted(sources.items()):
        hop = min(len(source.path) - 1 for source in paths)
        findings.append(IndirectModuleImpact(
            f"module-indirect:{module}", module, target_by_module[module], f"indirect_{hop}hop",
            hop, hop + 1, tuple(paths),
        ))
    return tuple(findings)
