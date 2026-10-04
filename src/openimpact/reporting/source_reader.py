"""Reuse the frozen source-reading guards for additional evidence domains."""

from pathlib import Path

from openimpact.analysis.models import SourceLocation
from openimpact.reporting.evidence import EvidenceBuilder, EvidenceDiagnostic


def read_source_snapshot(root: Path, file: str, line: int, column: int,
                         end_line: int, expected_hash: str | None = None):
    location, snippet, digest, diagnostics = EvidenceBuilder(root)._read_source(
        Path(file), SourceLocation(line, column, end_line),
    )
    if expected_hash is not None and digest is not None and digest != expected_hash:
        snippet = None
        diagnostics = (*diagnostics, EvidenceDiagnostic("source_snapshot_mismatch", "证据源码已变化，不能使用旧位置的片段。"))
    return location, snippet, digest, diagnostics
