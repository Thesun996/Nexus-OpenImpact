"""Validated inputs and outputs for explanations of existing evidence only."""

from dataclasses import asdict, dataclass
import math
from pathlib import Path
from typing import Any, Literal

from openimpact.reporting.evidence import EvidenceLocation, EvidencePath, ImpactEvidence

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
    return ExplanationResult(
        summary=summary,
        why_affected=why,
        risk_level="unknown",
        suggested_check=suggested,
        confidence=1.0,
    )
