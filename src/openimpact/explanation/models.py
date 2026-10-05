"""Validated inputs and outputs for explanations of existing evidence only."""

from dataclasses import asdict, dataclass
import math
from pathlib import Path
from typing import Any, Literal

from openimpact.reporting.evidence import EvidenceLocation, EvidencePath, ImpactEvidence
from openimpact.explanation.context import ExplanationContext

RiskLevel = Literal["low", "medium", "high", "unknown"]


def _required_text(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} 必须是非空字符串。")


def _valid_location(location: EvidenceLocation) -> bool:
    file = location.file
    return (isinstance(file, Path) and not file.is_absolute() and not file.drive
            and not file.root and file.parts
            and ".." not in file.parts and isinstance(location.line, int)
            and not isinstance(location.line, bool) and location.line >= 1
            and isinstance(location.column, int) and not isinstance(location.column, bool)
            and location.column >= 0 and (location.end_line is None or (
                isinstance(location.end_line, int) and not isinstance(location.end_line, bool)
                and location.end_line >= location.line
            )))


@dataclass(frozen=True)
class ExplanationInput:
    target_symbol: str
    change_description: str
    impact_type: Literal["direct", "indirect_1hop", "indirect_2hop"]
    source_location: EvidenceLocation
    source_snippet: str
    rule: str
    reason: str
    propagation_path: tuple[EvidencePath, ...]
    context: ExplanationContext | None = None

    def __post_init__(self) -> None:
        for field in ("target_symbol", "change_description", "source_snippet", "rule", "reason"):
            _required_text(getattr(self, field), field)
        if self.impact_type not in ("direct", "indirect_1hop", "indirect_2hop"):
            raise ValueError("impact_type 不受支持。")
        if not isinstance(self.source_location, EvidenceLocation) or not _valid_location(
            self.source_location
        ):
            raise ValueError("source_location 必须是有效的项目相对源码位置。")
        if not isinstance(self.propagation_path, tuple) or any(
            not isinstance(path, EvidencePath)
            or not isinstance(path.symbols, tuple)
            or any(not isinstance(symbol, str) or not symbol.strip()
                   for symbol in path.symbols)
            or not isinstance(path.call_sites, tuple)
            or len(path.symbols) < 2
            or len(path.call_sites) != len(path.symbols) - 1
            or path.symbols[-1] != self.target_symbol
            or any(not _valid_location(site) for site in path.call_sites)
            for path in self.propagation_path
        ):
            raise ValueError("propagation_path 必须包含完整的项目相对调用路径。")
        if self.impact_type == "direct" and self.propagation_path:
            raise ValueError("Direct 解释不能包含间接传播路径。")
        if self.impact_type != "direct" and not self.propagation_path:
            raise ValueError("Indirect 的 propagation_path 需要至少一条传播路径。")
        if self.context is not None:
            if not isinstance(self.context, ExplanationContext):
                raise ValueError('context 必须是结构化证据上下文。')
            first, last = self.context.steps[0], self.context.steps[-1]
            if (first.file, first.line, first.column) != (
                self.source_location.file.as_posix(), self.source_location.line, self.source_location.column
            ) or last.callee != self.target_symbol:
                raise ValueError('context 与当前证据不对应。')
            symbols = (first.caller, *(step.callee for step in self.context.steps))
            if self.impact_type == 'direct' and len(self.context.steps) != 1:
                raise ValueError('直接影响不能带有推测的上游路径。')
            if self.propagation_path and not any(symbols == path.symbols and all(
                (step.file, step.line, step.column) == (site.file.as_posix(), site.line, site.column)
                for step, site in zip(self.context.steps, path.call_sites)
            ) for path in self.propagation_path):
                raise ValueError('context 必须对应已有传播路径及真实位置。')

    @classmethod
    def from_evidence(
        cls, evidence: ImpactEvidence, change_description: str
    ) -> "ExplanationInput":
        """Accept only source-backed evidence; never infer absent source facts."""
        if not isinstance(evidence, ImpactEvidence):
            raise TypeError("evidence 必须是 ImpactEvidence。")
        if evidence.diagnostics or evidence.location is None or evidence.source_snippet is None \
                or evidence.source_hash is None:
            raise ValueError("Evidence 不完整，无法生成解释输入。")
        return cls(
            target_symbol=evidence.target_symbol,
            change_description=change_description,
            impact_type=evidence.impact_type,
            source_location=evidence.location,
            source_snippet=evidence.source_snippet,
            rule=evidence.rule,
            reason=evidence.reason,
            propagation_path=evidence.propagation_path,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready contract without absolute filesystem paths."""
        return {
            **({'context': self.context.to_dict()} if self.context is not None else {}),
            "target_symbol": self.target_symbol,
            "change_description": self.change_description,
            "impact_type": self.impact_type,
            "source_location": _location_data(self.source_location),
            "source_snippet": self.source_snippet,
            "rule": self.rule,
            "reason": self.reason,
            "propagation_path": [
                {
                    "symbols": list(path.symbols),
                    "call_sites": [_location_data(site) for site in path.call_sites],
                    "direct_evidence_reference": path.direct_evidence_reference,
                }
                for path in self.propagation_path
            ],
        }


def _location_data(location: EvidenceLocation) -> dict[str, Any]:
    return {
        "file": location.file.as_posix(),
        "line": location.line,
        "column": location.column,
        "end_line": location.end_line,
    }


@dataclass(frozen=True)
class ExplanationResult:
    """Confidence measures fidelity to supplied facts, not runtime failure probability."""

    summary: str
    why_affected: str
    risk_level: RiskLevel
    suggested_check: str
    confidence: float

    def __post_init__(self) -> None:
        for field in ("summary", "why_affected", "suggested_check"):
            _required_text(getattr(self, field), field)
        if self.risk_level not in ("low", "medium", "high", "unknown"):
            raise ValueError("risk_level 不受支持。")
        if (isinstance(self.confidence, bool)
                or not isinstance(self.confidence, (int, float))
                or not math.isfinite(self.confidence)
                or not 0 <= self.confidence <= 1):
            raise ValueError("confidence 必须是 0 到 1 之间的有限数值。")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _reader_change_description(data: ExplanationInput) -> str:
    """Localize only the canonical add description's kind suffix; preserve identifiers."""
    description = data.change_description
    if description.startswith(f"{data.target_symbol} 新增必填参数 "):
        for kind, label in (
            ("positional_only", "仅按位置传入"),
            ("positional_or_keyword", "可按位置或参数名传入"),
            ("keyword_only", "仅按参数名传入"),
        ):
            suffix = f"（{kind}）"
            if description.endswith(suffix):
                return description[:-len(suffix)] + f"（{label}）"
    return description


def fallback_explanation(data: ExplanationInput) -> ExplanationResult:
    """Explain supplied facts deterministically; confidence measures evidence fidelity."""
    if not isinstance(data, ExplanationInput):
        raise TypeError("fallback_explanation 需要有效的 ExplanationInput。")
    location = data.source_location
    site = f"{location.file.as_posix()}:{location.line}"
    description = _reader_change_description(data)
    if data.impact_type == "direct":
        summary = f"{site} 对 {data.target_symbol} 的调用因本次变更已确定不兼容。"
        why = (f"变更：{description}。源码：{data.source_snippet.strip()}。"
               f"判断依据：{data.reason}")
        suggested = f"检查 {site} 的调用参数，并在修改后运行相关测试。"
    else:
        paths = [" → ".join(path.symbols) for path in data.propagation_path]
        summary = f"{site} 位于 {data.target_symbol} 的上游调用路径，建议检查。"
        reason = data.reason.replace("确定 Direct Impact 的上游调用路径", "确定直接影响的上游调用路径")
        why = (f"变更：{description}。源码：{data.source_snippet.strip()}。判断依据：{reason} "
               f"路径：{'；'.join(paths)}。静态路径不保证运行时失败。")
        suggested = f"沿上游路径检查 {site} 的调用及相关测试。"
    if data.context is not None:
        context = data.context
        terminal = context.steps[-1]
        why = (f'变更：{description}。\n当前证据：{data.source_snippet.strip()}。'
               f'\n原始直接调用 {terminal.site} 的兼容性依据：修改前，{context.before_reason} '
               f'修改后，{context.after_reason}')
        if data.impact_type != 'direct':
            why += (f'\n确定发生新不兼容的位置是 {terminal.site}；当前上游记录只说明静态调用路径相连。'
                    f'\n代表路径：{" → ".join((context.steps[0].caller, *(step.callee for step in context.steps)))}。'
                    '静态路径不保证运行时失败。')
        checks = [f'1. 先核对 {terminal.site}：{terminal.expression or "该位置的调用源码未能复核，请手动打开原文件"}。'
                  f'对照修改后签名，具体问题是：{context.after_reason}']
        question = {
            'add_required_parameter': '检查新增参数所需信息能否由此层提供，还是需要由上游传入；值的来源需人工确认。',
            'remove_parameter': '检查此层是否仍需要被删除参数所承载的信息，以及当前实参的去向；不能只删掉实参就认定业务正确。',
            'rename_parameter': '检查这段调用是否继续使用旧参数名；位置调用与按参数名调用的影响不同，需按实际调用方式核对。',
            'make_parameter_required': '检查此层是否依赖省略参数时的原默认值，以及改为显式传入后应由谁提供该值。',
        }[context.change_type]
        checks[0] += question
        if context.change_type == 'make_parameter_required':
            before = {parameter.name: parameter for parameter in context.before_signature.parameters}
            changed = [before[parameter.name] for parameter in context.after_signature.parameters
                       if parameter.name in before and before[parameter.name].has_default and not parameter.has_default]
            if len(changed) == 1 and changed[0].default_source is not None:
                checks[0] += f'原默认值的源码是 {changed[0].default_source[:200]}，此处没有执行该表达式。'
        # Start at the direct site and work outwards, using only supplied edges.
        for number, step in enumerate(reversed(context.steps[:-1]), 2):
            checks.append(f'{number}. 再看 {step.site}（{step.caller} → {step.callee}）：'
                          f'{step.expression or "调用源码未能复核，请手动核对该位置"}。'
                          '检查这一层是否需要配合调整接口或传参；现有证据没有证明需要怎样调整。'
                          '该上游位置未被判定为参数不兼容，仅按静态路径建议检查。')
        checks.append(f'{len(checks) + 1}. 人工检查现有测试是否覆盖上述调用及上游入口；'
                      '测试位置和执行结果未提供，需自行确认后运行。')
        checks.append('业务边界：这里没有执行源码，不能确定输入取值、业务后果或运行时是否走到这条路径。')
        if context.path_count > 1:
            checks.append(f'该记录关联 {context.path_count} 个直接影响来源；上面仅展开一条代表路径，其他路径请查看源码证据。')
        if context.incomplete_analysis:
            checks.append('覆盖提示：项目含未解析或未支持内容，以上检查范围不能代表整个项目。')
        suggested = '\n'.join(checks)
    return ExplanationResult(
        summary=summary,
        why_affected=why,
        risk_level="unknown",
        suggested_check=suggested,
        confidence=1.0,
    )
