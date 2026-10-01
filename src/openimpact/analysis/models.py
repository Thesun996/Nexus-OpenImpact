"""Immutable syntax facts produced for one Python source file."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ParameterKind = Literal[
    "positional_only",
    "positional_or_keyword",
    "keyword_only",
    "var_positional",
    "var_keyword",
]
ImportType = Literal["import", "from_import"]
CallExpressionType = Literal["name", "attribute", "other"]
DiagnosticKind = Literal["read_error", "encoding_error", "syntax_error"]


@dataclass(frozen=True)
class Parameter:
    name: str
    kind: ParameterKind
    has_default: bool = False
    default_source: str | None = None
    annotation_source: str | None = None


@dataclass(frozen=True)
class FunctionDefinition:
    name: str
    lineno: int
    end_lineno: int | None
    parameters: tuple[Parameter, ...]
    is_async: bool = False
    local_bindings: frozenset[str] = frozenset()
    return_annotation_source: str | None = None


@dataclass(frozen=True)
class ImportReference:
    import_type: ImportType
    module: str | None
    imported_name: str | None
    alias: str | None
    level: int
    lineno: int
    end_lineno: int | None


@dataclass(frozen=True)
class FunctionCall:
    """A call in module scope or a module-level function; callee stays unbound."""

    file: Path
    lineno: int
    col_offset: int
    end_lineno: int | None
    expression_type: CallExpressionType
    expression: str
    callee_path: tuple[str, ...] | None
    enclosing_function: str | None
    positional_count: int
    keyword_names: frozenset[str]
    has_star_args: bool
    has_star_kwargs: bool
    call_expression: str | None = None


@dataclass(frozen=True)
class SourceLocation:
    """A stable source span beginning at a zero-based AST column."""

    line: int
    column: int
    end_line: int | None = None


@dataclass(frozen=True)
class ParseDiagnostic:
    kind: DiagnosticKind
    message: str
    lineno: int | None = None
    col_offset: int | None = None


@dataclass(frozen=True)
class ParsedModule:
    path: Path
    functions: tuple[FunctionDefinition, ...]
    imports: tuple[ImportReference, ...]
    calls: tuple[FunctionCall, ...]
    diagnostics: tuple[ParseDiagnostic, ...] = ()
    module_rebindings: frozenset[str] = frozenset()
