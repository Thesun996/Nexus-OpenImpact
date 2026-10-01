"""Build source-backed evidence from existing impact findings."""

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import tokenize
from typing import Literal

from openimpact.analysis.direct_impact import ImpactFinding
from openimpact.analysis.indirect_impact import IndirectImpactFinding
from openimpact.analysis.models import SourceLocation


@dataclass(frozen=True)
class EvidenceLocation:
    file: Path  # Relative to the inspected project.
    line: int
    column: int
    end_line: int | None = None


@dataclass(frozen=True)
class EvidencePath:
    """One upstream-to-target path and the Direct Impact that anchors it."""

    symbols: tuple[str, ...]
    call_sites: tuple[EvidenceLocation, ...]
    direct_evidence_reference: str | None


@dataclass(frozen=True)
class EvidenceDiagnostic:
    code: str
    message: str


@dataclass(frozen=True)
class ImpactEvidence:
    impact_type: Literal["direct", "indirect_1hop", "indirect_2hop"]
    target_symbol: str
    location: EvidenceLocation | None
    source_snippet: str | None
    source_hash: str | None  # SHA-256 of the complete source file bytes.
    rule: str
    reason: str
    propagation_path: tuple[EvidencePath, ...]
    call_expression: str | None = None
    evidence_reference: str | None = None
    diagnostics: tuple[EvidenceDiagnostic, ...] = ()


class EvidenceBuilder:
    """Read a project snapshot; never import or execute its Python files."""

    def __init__(self, project_root: str | Path):
        self.project_root = Path(project_root).resolve()

    def build(self, finding: ImpactFinding | IndirectImpactFinding) -> ImpactEvidence:
        if isinstance(finding, ImpactFinding):
            source_file = finding.source_file or finding.assessment.file
            source_location = finding.source_location or SourceLocation(
                finding.assessment.line, finding.assessment.col_offset
            )
            target_symbol = finding.target_symbol or finding.assessment.target_symbol_id
            rule = finding.rule_id
            paths: tuple[EvidencePath, ...] = ()
        else:
            source_file = finding.source_file
            source_location = finding.source_location
            target_symbol = finding.target_symbol or (
                finding.sources[0].source_direct_impact.assessment.target_symbol_id
                if finding.sources else ""
            )
            rule = "resolved_upstream_call_path"
            paths = tuple(
                EvidencePath(
                    symbols=(source.propagation_path[0].caller_symbol_id, *(
                        edge.callee_symbol_id for edge in source.propagation_path
                    )),
                    call_sites=tuple(
                        EvidenceLocation(edge.file, edge.line, edge.col_offset)
                        for edge in source.propagation_path
                    ),
                    direct_evidence_reference=source.evidence_reference,
                )
                for source in finding.sources if source.propagation_path
            )

        location, snippet, digest, diagnostics = self._read_source(
            source_file, source_location
        )
        return ImpactEvidence(
            impact_type=finding.impact_type,
            target_symbol=target_symbol,
            location=location,
            source_snippet=snippet,
            source_hash=digest,
            rule=rule,
            reason=finding.reason,
            propagation_path=paths,
            call_expression=finding.call_expression,
            evidence_reference=finding.evidence_reference,
            diagnostics=diagnostics,
        )

    def _read_source(
        self, source_file: Path | None, source_location: SourceLocation | None
    ) -> tuple[EvidenceLocation | None, str | None, str | None,
               tuple[EvidenceDiagnostic, ...]]:
        if source_file is None or source_location is None:
            return None, None, None, (
                EvidenceDiagnostic("missing_location", "影响记录缺少源码位置。"),
            )
        relative_file = Path(source_file)
        if relative_file.is_absolute() or ".." in relative_file.parts:
            return None, None, None, (
                EvidenceDiagnostic("invalid_path", "源码路径必须位于项目目录内。"),
            )
        candidate = (self.project_root / relative_file).resolve()
        if not candidate.is_relative_to(self.project_root):
            return None, None, None, (
                EvidenceDiagnostic("invalid_path", "源码路径必须位于项目目录内。"),
            )
        location = EvidenceLocation(
            relative_file, source_location.line, source_location.column,
            source_location.end_line,
        )
        try:
            raw = candidate.read_bytes()
        except FileNotFoundError:
            return location, None, None, (
                EvidenceDiagnostic("file_missing", "证据对应的源码文件不存在。"),
            )
        except OSError:
            return location, None, None, (
                EvidenceDiagnostic("read_error", "无法读取证据对应的源码文件。"),
            )
        digest = sha256(raw).hexdigest()
        try:
            encoding, _ = tokenize.detect_encoding(BytesIO(raw).readline)
            lines = raw.decode(encoding).splitlines()
        except (SyntaxError, UnicodeError, LookupError):
            return location, None, digest, (
                EvidenceDiagnostic("encoding_error", "无法按 Python 源码编码读取证据。"),
            )
        start = source_location.line
        end = source_location.end_line or start
        if start < 1 or end < start or end > len(lines):
            return location, None, digest, (
                EvidenceDiagnostic("invalid_line", "证据行号超出源码范围。"),
            )
        return location, "\n".join(lines[start - 1:end]), digest, ()
