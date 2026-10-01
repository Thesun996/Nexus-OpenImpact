"""Describe and validate one proposed required-parameter addition."""

import ast
import keyword
from dataclasses import dataclass
from typing import Literal

from openimpact.analysis.models import FunctionDefinition, Parameter, ParameterKind
from openimpact.analysis.symbol_index import SymbolIndex

ChangeType = Literal["add_required_parameter"]
AddedParameterKind = Literal["positional_only", "positional_or_keyword", "keyword_only"]


@dataclass(frozen=True)
class FunctionSignature:
    name: str
    parameters: tuple[Parameter, ...]
    is_async: bool = False
    return_annotation_source: str | None = None

    @classmethod
    def from_definition(cls, definition: FunctionDefinition) -> "FunctionSignature":
        return cls(
            definition.name,
            definition.parameters,
            definition.is_async,
            definition.return_annotation_source,
        )


@dataclass(frozen=True)
class AddedParameter:
    name: str
    kind: AddedParameterKind
    required: bool = True
    annotation_source: str | None = None


@dataclass(frozen=True)
class ChangeSpec:
    change_type: ChangeType
    target_symbol_id: str
    before: FunctionSignature
    after: FunctionSignature
    added_parameter: AddedParameter


@dataclass(frozen=True)
class ChangeDiagnostic:
    code: str
    message: str


@dataclass(frozen=True)
class ChangeValidationResult:
    valid: bool
    current_signature: FunctionSignature | None
    diagnostics: tuple[ChangeDiagnostic, ...]


def _failure(
    current: FunctionSignature | None, code: str, message: str
) -> ChangeValidationResult:
    return ChangeValidationResult(False, current, (ChangeDiagnostic(code, message),))


def _valid_identifier(name: str) -> bool:
    return isinstance(name, str) and name.isidentifier() and not keyword.iskeyword(name)


def _valid_expression(source: str | None) -> bool:
    if source is None:
        return True
    if not isinstance(source, str) or not source.strip():
        return False
    try:
        ast.parse(source, mode="eval")
    except SyntaxError:
        return False
    return True


_KINDS: tuple[ParameterKind, ...] = (
    "positional_only", "positional_or_keyword", "var_positional", "keyword_only", "var_keyword"
)


def _signature_is_valid(signature: FunctionSignature) -> bool:
    """Check Python parameter ordering without parsing user-written signatures."""
    if not _valid_identifier(signature.name) or not _valid_expression(
        signature.return_annotation_source
    ):
        return False
    names: set[str] = set()
    previous_group = -1
    optional_positional_seen = False
    var_positional_seen = False
    var_keyword_seen = False
    for parameter in signature.parameters:
        if (
            not _valid_identifier(parameter.name)
            or parameter.name in names
            or parameter.kind not in _KINDS
            or (parameter.default_source is not None and not parameter.has_default)
            or not _valid_expression(parameter.default_source)
            or not _valid_expression(parameter.annotation_source)
        ):
            return False
        names.add(parameter.name)
        group = _KINDS.index(parameter.kind)
        if group < previous_group:
            return False
        previous_group = group
        if parameter.kind in ("positional_only", "positional_or_keyword"):
            if parameter.has_default:
                optional_positional_seen = True
            elif optional_positional_seen:
                return False
        elif parameter.kind == "var_positional":
            if var_positional_seen or parameter.has_default:
                return False
            var_positional_seen = True
        elif parameter.kind == "var_keyword":
            if var_keyword_seen or parameter.has_default:
                return False
            var_keyword_seen = True
    return True


def validate_change_spec(index: SymbolIndex, spec: ChangeSpec) -> ChangeValidationResult:
    """Validate the declaration using in-memory symbols; never write project files."""
    if spec.change_type != "add_required_parameter":
        return _failure(None, "unsupported_change_type", "当前仅支持新增必填参数。")
    symbol = index.symbols.get(spec.target_symbol_id)
    if symbol is None:
        return _failure(None, "target_not_found", "项目索引中没有这个模块级函数。")
    if not isinstance(symbol.definition, FunctionDefinition):
        return _failure(None, "unsupported_target", "当前目标需要是模块级函数。")
    current = FunctionSignature.from_definition(symbol.definition)
    if spec.before != current:
        return _failure(current, "before_mismatch", "声明的当前签名与源码不一致。")
    if not _signature_is_valid(spec.after):
        return _failure(current, "invalid_after_signature", "目标签名不符合 Python 参数规则。")
    if (
        spec.after.name != current.name
        or spec.after.is_async != current.is_async
        or spec.after.return_annotation_source != current.return_annotation_source
        or len(spec.after.parameters) != len(current.parameters) + 1
    ):
        return _failure(current, "unsupported_change_shape", "本次变化只能新增一个参数。")

    insertion = [
        parameter
        for position, parameter in enumerate(spec.after.parameters)
        if (
            spec.after.parameters[:position] + spec.after.parameters[position + 1:]
            == current.parameters
        )
    ]
    if len(insertion) != 1:
        return _failure(current, "unsupported_change_shape", "原有参数不能删除、重命名或更改。")
    added = insertion[0]
    if added.kind not in ("positional_only", "positional_or_keyword", "keyword_only"):
        return _failure(current, "unsupported_parameter_kind", "新增参数必须是普通或仅关键字参数。")
    if (
        added.name != spec.added_parameter.name
        or added.kind != spec.added_parameter.kind
        or added.annotation_source != spec.added_parameter.annotation_source
    ):
        return _failure(current, "added_parameter_mismatch", "新增参数声明与目标签名不一致。")
    if not spec.added_parameter.required or added.has_default:
        return _failure(current, "added_parameter_not_required", "新增参数带默认值或被声明为可选。")
    return ChangeValidationResult(True, current, ())
