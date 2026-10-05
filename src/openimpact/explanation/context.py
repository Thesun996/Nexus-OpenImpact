"""Bounded explanation context from existing findings, never new impact analysis."""

from dataclasses import asdict, dataclass
from pathlib import Path

from openimpact.reporting.source_reader import read_source_snapshot
from openimpact.analysis.change_spec import FunctionSignature


@dataclass(frozen=True)
class CallStep:
    caller: str
    callee: str
    file: str
    line: int
    column: int
    expression: str | None
    source_hash: str | None

    def __post_init__(self):
        path = Path(self.file)
        if path.is_absolute() or path.drive or path.root or '..' in path.parts:
            raise ValueError('解释位置必须是项目相对路径。')
        if not self.file or self.line < 1 or self.column < 0:
            raise ValueError('解释位置无效。')

    @property
    def site(self):
        return f'{self.file}:{self.line}:{self.column}'


@dataclass(frozen=True)
class ExplanationContext:
    steps: tuple[CallStep, ...]
    before_reason: str
    after_reason: str
    path_count: int
    incomplete_analysis: bool
    change_type: str
    before_signature: FunctionSignature
    after_signature: FunctionSignature

    def __post_init__(self):
        if not isinstance(self.steps, tuple) or not 1 <= len(self.steps) <= 3:
            raise ValueError('解释只接收一条最多三条调用边的代表路径。')
        if any(not isinstance(step, CallStep) for step in self.steps):
            raise ValueError('解释调用位置无效。')
        if any(a.callee != b.caller for a, b in zip(self.steps, self.steps[1:])):
            raise ValueError('解释路径必须连续。')
        if not self.before_reason or not self.after_reason or self.path_count < 1:
            raise ValueError('解释缺少已有兼容性依据。')
        if self.change_type not in {'add_required_parameter', 'remove_parameter',
                                   'rename_parameter', 'make_parameter_required'}:
            raise ValueError('解释上下文变更类型无效。')
        if not isinstance(self.before_signature, FunctionSignature) or not isinstance(self.after_signature, FunctionSignature):
            raise ValueError('解释必须使用既有结构化签名。')

    def to_dict(self):
        return asdict(self)


def build_explanation_context(run, finding, evidence):
    """Attach one existing representative path and verified call expressions only.

    Missing/changed source leaves an explicit missing expression; graph facts and
    compatibility assessments stay as calculated. No import/call rebinding occurs.
    """
    if hasattr(finding, 'assessment'):
        assessment = finding.assessment
        edges = [edge for edge in run.graph.edges
                 if (edge.file, edge.line, edge.col_offset, edge.caller_symbol_id,
                     edge.callee_symbol_id) == (assessment.file, assessment.line,
                     assessment.col_offset, assessment.caller_symbol_id, assessment.target_symbol_id)]
        if len(edges) != 1:
            raise ValueError('缺少唯一的既有调用边。')
        count = 1
    else:
        # Same representative as EvidenceBuilder, so context cannot change selection.
        source = min(finding.sources, key=lambda item: len(item.propagation_path))
        edges = source.propagation_path
        assessment = source.source_direct_impact.assessment
        count = len(finding.sources)
    if assessment.effect != 'direct_impact':
        raise ValueError('解释上下文必须以确定直接影响结束。')
    calls = {(file, call.lineno, call.col_offset): call
             for module, file in run.index.modules.items()
             for call in run.index.parsed_modules[module].calls}
    steps = []
    for edge in edges:
        call = calls.get((edge.file, edge.line, edge.col_offset))
        expression, digest = None, None
        if call is not None and call.call_expression:
            try:
                expected = evidence.source_hash if edge.file == evidence.location.file else None
                _, snippet, current_hash, diagnostics = read_source_snapshot(
                    run.project_path, edge.file.as_posix(), edge.line, edge.col_offset,
                    call.end_lineno or call.lineno, expected)
                # AST captures the original exact source segment. Check it still
                # starts at the recorded UTF-8 column, not merely somewhere in file.
                at_column = (snippet.splitlines()[0].encode('utf-8')[edge.col_offset:].decode('utf-8')
                             if snippet is not None else '')
                if not diagnostics and snippet is not None and at_column.startswith(call.call_expression.splitlines()[0]) \
                        and call.call_expression in snippet:
                    expression, digest = call.call_expression[:800], current_hash
            except (OSError, ValueError, UnicodeError):
                pass
        steps.append(CallStep(edge.caller_symbol_id, edge.callee_symbol_id,
                              edge.file.as_posix(), edge.line, edge.col_offset, expression, digest))
    partial = bool(run.index.parse_diagnostics or run.graph.unresolved_calls
                   or run.index.ambiguous_modules or run.index.ambiguous_symbols
                   or run.index.unsupported_scope_diagnostics()
                   or any(binding.status == 'unresolved' for bindings in run.index.bindings.values()
                          for binding in bindings.values()))
    return ExplanationContext(tuple(steps), assessment.before_reason,
                              assessment.after_reason, count, partial,
                              run.change_spec.change_type,
                              run.change_spec.before_signature, run.change_spec.after_signature)
