"""Check resolved calls against one validated required-parameter addition."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from openimpact.analysis.call_graph import CallEdge, CallGraph
from openimpact.analysis.change_spec import (
    ChangeSpec,
    ChangeValidationResult,
    FunctionSignature,
    validate_change_spec,
)
from openimpact.analysis.models import FunctionCall

CompatibilityStatus = Literal["compatible", "incompatible", "manual_review"]
ChangeEffect = Literal[
    "direct_impact", "no_impact", "pre_existing_problem",
    "compatibility_improved", "manual_review",
]


@dataclass(frozen=True)
class CompatibilityResult:
    status: CompatibilityStatus
    rule_id: str
    reason: str


@dataclass(frozen=True)
class CallCompatibilityAssessment:
    """Before/after binding results for one resolved call location."""

    change_spec: ChangeSpec
    caller_symbol_id: str
    target_symbol_id: str
    file: Path
    line: int
    col_offset: int
    resolution_basis: str
    before_status: CompatibilityStatus
    after_status: CompatibilityStatus
    before_reason: str
    after_reason: str
    before_rule_id: str
    after_rule_id: str
    effect: ChangeEffect


@dataclass(frozen=True)
class ImpactFinding:
    """A change-caused direct break or a call requiring manual review."""

    assessment: CallCompatibilityAssessment
    impact_type: Literal["direct"]
    effect: Literal["direct_impact", "manual_review"]
    rule_id: str
    reason: str


@dataclass(frozen=True)
class DirectImpactResult:
    validation: ChangeValidationResult
    assessments: tuple[CallCompatibilityAssessment, ...]
    findings: tuple[ImpactFinding, ...]

    @property
    def direct_impact_count(self) -> int:
        return sum(finding.effect == "direct_impact" for finding in self.findings)


def check_call_compatibility(
    call: FunctionCall, signature: FunctionSignature
) -> CompatibilityResult:
    """Bind known argument shapes to a signature without evaluating expressions."""
    if call.has_star_args or call.has_star_kwargs:
        return CompatibilityResult(
            "manual_review", "argument_expansion_unknown",
            "调用包含 *args 或 **kwargs，无法静态确定展开后的参数。",
        )

    positional = [
        parameter for parameter in signature.parameters
        if parameter.kind in ("positional_only", "positional_or_keyword")
    ]
    by_name = {parameter.name: parameter for parameter in signature.parameters}
    has_var_positional = any(
        parameter.kind == "var_positional" for parameter in signature.parameters
    )
    has_var_keyword = any(
        parameter.kind == "var_keyword" for parameter in signature.parameters
    )
    if call.positional_count > len(positional) and not has_var_positional:
        return CompatibilityResult(
            "incompatible", "too_many_positional_arguments", "位置参数数量超过该签名允许的数量。"
        )

    supplied = {parameter.name for parameter in positional[:call.positional_count]}
    for name in sorted(call.keyword_names):
        parameter = by_name.get(name)
        if parameter is None or parameter.kind in (
            "positional_only", "var_positional", "var_keyword"
        ):
            # A positional-only name can also be an unrelated **kwargs key.
            if has_var_keyword:
                continue
            return CompatibilityResult(
                "incompatible", "unexpected_keyword_argument",
                f"关键字参数 {name} 无法绑定到该签名。",
            )
        if name in supplied:
            return CompatibilityResult(
                "incompatible", "multiple_values_for_parameter",
                f"参数 {name} 同时由位置参数和关键字参数提供。",
            )
        supplied.add(name)

    for parameter in signature.parameters:
        if parameter.kind in (
            "positional_only", "positional_or_keyword", "keyword_only"
        ) and not parameter.has_default and parameter.name not in supplied:
            return CompatibilityResult(
                "incompatible", "required_parameter_missing",
                f"该签名的必填参数 {parameter.name} 未由当前调用提供。",
            )
    return CompatibilityResult(
        "compatible", "arguments_bind", "当前调用的确定参数可绑定到该签名。"
    )


def _change_effect(before: CompatibilityStatus, after: CompatibilityStatus) -> ChangeEffect:
    if "manual_review" in (before, after):
        return "manual_review"
    if before == "compatible" and after == "incompatible":
        return "direct_impact"
    if before == "incompatible" and after == "incompatible":
        return "pre_existing_problem"
    if before == "incompatible" and after == "compatible":
        return "compatibility_improved"
    return "no_impact"


def analyze_direct_impact(graph: CallGraph, spec: ChangeSpec) -> DirectImpactResult:
    """Assess only resolved edges to the requested symbol; do not traverse the graph."""
    validation = validate_change_spec(graph.index, spec)
    if not validation.valid:
        return DirectImpactResult(validation, (), ())

    calls: dict[tuple[Path, int, int, str], FunctionCall] = {}
    for module, path in graph.index.modules.items():
        for call in graph.index.parsed_modules[module].calls:
            if call.enclosing_function is not None:
                key = (path, call.lineno, call.col_offset, f"{module}.{call.enclosing_function}")
                calls[key] = call

    assessments: list[CallCompatibilityAssessment] = []
    findings: list[ImpactFinding] = []
    edges = sorted(
        (edge for edge in graph.edges if edge.callee_symbol_id == spec.target_symbol_id),
        key=lambda edge: (edge.file.as_posix(), edge.line, edge.col_offset,
                          edge.caller_symbol_id),
    )
    for edge in edges:
        call = _call_for_edge(calls, edge)
        before = check_call_compatibility(call, spec.before)
        after = check_call_compatibility(call, spec.after)
        effect = _change_effect(before.status, after.status)
        assessment = CallCompatibilityAssessment(
            spec, edge.caller_symbol_id, edge.callee_symbol_id, edge.file,
            edge.line, edge.col_offset, edge.basis,
            before.status, after.status, before.reason, after.reason,
            before.rule_id, after.rule_id, effect,
        )
        assessments.append(assessment)
        if effect == "direct_impact":
            findings.append(ImpactFinding(
                assessment, "direct", effect, "required_parameter_added_breaks_call",
                f"修改前调用兼容；修改后{after.reason}",
            ))
        elif effect == "manual_review":
            findings.append(ImpactFinding(
                assessment, "direct", effect, "argument_expansion_unknown",
                "修改前或修改后的参数绑定无法静态确定，需要人工检查。",
            ))
    return DirectImpactResult(validation, tuple(assessments), tuple(findings))


def _call_for_edge(
    calls: dict[tuple[Path, int, int, str], FunctionCall], edge: CallEdge
) -> FunctionCall:
    key = (edge.file, edge.line, edge.col_offset, edge.caller_symbol_id)
    try:
        return calls[key]
    except KeyError as error:
        raise ValueError("调用边缺少对应的 AST 调用事实；请重新构建索引与调用图。") from error
