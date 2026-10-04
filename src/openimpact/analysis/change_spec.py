"""Canonical signatures, typed change intent, and operation-specific validation."""

import ast
import keyword
from dataclasses import asdict, dataclass, field, replace
from enum import Enum
from types import MappingProxyType
from typing import Any, ClassVar, Literal, TypeAlias
from unicodedata import normalize

from openimpact.analysis.models import FunctionDefinition, Parameter, ParameterKind
from openimpact.analysis.symbol_index import SymbolIndex


class ChangeType(str, Enum):
    ADD_REQUIRED_PARAMETER = "add_required_parameter"
    REMOVE_PARAMETER = "remove_parameter"
    RENAME_PARAMETER = "rename_parameter"
    MAKE_PARAMETER_REQUIRED = "make_parameter_required"


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
class ChangeDiagnostic:
    code: str
    message: str


@dataclass(frozen=True)
class ChangeValidationResult:
    valid: bool
    current_signature: FunctionSignature | None
    diagnostics: tuple[ChangeDiagnostic, ...]


class ChangeOperationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class AddRequiredParameterOperation:
    added_parameter: AddedParameter
    insert_before: str | None = None
    change_type: Literal[ChangeType.ADD_REQUIRED_PARAMETER] = field(
        default=ChangeType.ADD_REQUIRED_PARAMETER, init=False
    )
    direct_rule_id: ClassVar[str] = "required_parameter_added_breaks_call"

    @property
    def legacy_added_parameter(self) -> AddedParameter:
        """Compatibility view for the existing add-only ChangeSpec contract."""
        return self.added_parameter

    def __post_init__(self) -> None:
        if not isinstance(self.added_parameter, AddedParameter):
            raise ChangeOperationError("invalid_operation_payload", "operation 需要结构化新增参数。")
        if self.insert_before is not None and (
            not isinstance(self.insert_before, str) or not self.insert_before
        ):
            raise ChangeOperationError("invalid_operation_payload", "insert_before 必须是现有参数名称。")

    def payload_diagnostic(self) -> ChangeDiagnostic | None:
        added = self.added_parameter
        if not isinstance(added.name, str) or not added.name:
            return ChangeDiagnostic("invalid_operation_payload", "新增参数名必须是非空字符串。")
        if added.kind not in ("positional_only", "positional_or_keyword", "keyword_only"):
            return ChangeDiagnostic("unsupported_parameter_kind", "新增参数类型不受支持。")
        if added.required is not True:
            return ChangeDiagnostic("added_parameter_not_required", "新增参数必须声明为必填。")
        if added.annotation_source is not None and not isinstance(added.annotation_source, str):
            return ChangeDiagnostic("invalid_operation_payload", "参数注解必须是源码文本或 null。")
        return None

    def build_after(self, before: FunctionSignature) -> FunctionSignature:
        """Construct a draft once; Python legality remains in the shared validator."""
        if diagnostic := self.payload_diagnostic():
            raise ChangeOperationError(diagnostic.code, diagnostic.message)
        if self.insert_before is None:
            group = _KINDS.index(self.added_parameter.kind)
            position = next(
                (i for i, parameter in enumerate(before.parameters)
                 if _KINDS.index(parameter.kind) > group), len(before.parameters),
            )
        else:
            position = next(
                (i for i, parameter in enumerate(before.parameters)
                 if parameter.name == self.insert_before), None,
            )
            if position is None:
                raise ChangeOperationError("insert_before_not_found", "insert_before 未指向现有参数。")
        parameter = Parameter(
            self.added_parameter.name, self.added_parameter.kind, False,
            annotation_source=self.added_parameter.annotation_source,
        )
        return FunctionSignature(
            before.name, before.parameters[:position] + (parameter,) + before.parameters[position:],
            before.is_async, before.return_annotation_source,
        )

    def validate_delta(
        self, before: FunctionSignature, after: FunctionSignature
    ) -> ChangeDiagnostic | None:
        if (
            after.name != before.name or after.is_async != before.is_async
            or after.return_annotation_source != before.return_annotation_source
            or len(after.parameters) != len(before.parameters) + 1
        ):
            return ChangeDiagnostic("unsupported_change_shape", "本次变化只能新增一个参数。")
        insertion = [
            (position, parameter) for position, parameter in enumerate(after.parameters)
            if after.parameters[:position] + after.parameters[position + 1:] == before.parameters
        ]
        if len(insertion) != 1:
            return ChangeDiagnostic("unsupported_change_shape", "原有参数不能删除、重命名或更改。")
        position, added = insertion[0]
        if added.kind not in ("positional_only", "positional_or_keyword", "keyword_only"):
            return ChangeDiagnostic("unsupported_parameter_kind", "新增参数必须是普通或仅关键字参数。")
        if (added.name != self.added_parameter.name or added.kind != self.added_parameter.kind
                or added.annotation_source != self.added_parameter.annotation_source):
            return ChangeDiagnostic("added_parameter_mismatch", "新增参数声明与目标签名不一致。")
        if added.has_default:
            return ChangeDiagnostic("added_parameter_not_required", "新增参数带默认值或被声明为可选。")
        if diagnostic := self.payload_diagnostic():
            return diagnostic
        if self.insert_before is not None:
            expected = next((i for i, p in enumerate(before.parameters)
                             if p.name == self.insert_before), None)
            if expected is None:
                return ChangeDiagnostic("insert_before_not_found", "insert_before 未指向现有参数。")
            if position != expected:
                return ChangeDiagnostic("operation_signature_mismatch", "目标签名未遵循声明的插入位置。")
        return None

    def describe(self, target_symbol_id: str) -> str:
        return (f"{target_symbol_id} 新增必填参数 {self.added_parameter.name}"
                f"（{self.added_parameter.kind}）")

    def evidence_reason(self, target_symbol_id: str, reason: str) -> str:
        return reason

    def to_dict(self) -> dict[str, Any]:
        return {"change_type": self.change_type.value,
                "added_parameter": asdict(self.added_parameter), "insert_before": self.insert_before}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AddRequiredParameterOperation":
        if data.get("change_type") != ChangeType.ADD_REQUIRED_PARAMETER:
            raise ChangeOperationError("unsupported_change_type", "operation 类型与参数模型不一致。")
        if set(data) - {"change_type", "added_parameter", "insert_before"}:
            raise ChangeOperationError("invalid_operation_payload", "operation 包含不支持的字段。")
        added = data.get("added_parameter")
        if (not isinstance(added, dict) or set(added) - {
            "name", "kind", "required", "annotation_source"
        } or not {"name", "kind", "required"} <= set(added)):
            raise ChangeOperationError("invalid_operation_payload", "operation 新增参数字段不完整或不受支持。")
        operation = cls(AddedParameter(added["name"], added["kind"], added["required"],
                                       added.get("annotation_source")), data.get("insert_before"))
        if diagnostic := operation.payload_diagnostic():
            raise ChangeOperationError(diagnostic.code, diagnostic.message)
        return operation


@dataclass(frozen=True)
class RemoveParameterOperation:
    parameter_name: str
    change_type: Literal[ChangeType.REMOVE_PARAMETER] = field(
        default=ChangeType.REMOVE_PARAMETER, init=False
    )
    direct_rule_id: ClassVar[str] = "parameter_removed_breaks_call"

    def __post_init__(self) -> None:
        if not _valid_identifier(self.parameter_name):
            raise ChangeOperationError(
                "invalid_operation_payload", "parameter_name 必须是合法的 Python 参数名。"
            )

    @property
    def legacy_added_parameter(self) -> None:
        return None

    def _parameter_position(self, before: FunctionSignature) -> int:
        position = next((i for i, parameter in enumerate(before.parameters)
                         if parameter.name == self.parameter_name), None)
        if position is None:
            raise ChangeOperationError("parameter_not_found", "目标函数中没有指定的参数。")
        if before.parameters[position].kind not in (
            "positional_only", "positional_or_keyword", "keyword_only"
        ):
            raise ChangeOperationError(
                "unsupported_parameter_kind", "当前不支持删除 *args 或 **kwargs 参数。"
            )
        return position

    def build_after(self, before: FunctionSignature) -> FunctionSignature:
        position = self._parameter_position(before)
        return FunctionSignature(
            before.name, before.parameters[:position] + before.parameters[position + 1:],
            before.is_async, before.return_annotation_source,
        )

    def validate_delta(
        self, before: FunctionSignature, after: FunctionSignature
    ) -> ChangeDiagnostic | None:
        try:
            position = self._parameter_position(before)
        except ChangeOperationError as error:
            return ChangeDiagnostic(error.code, str(error))
        if (
            after.name != before.name
            or after.is_async != before.is_async
            or after.return_annotation_source != before.return_annotation_source
            or after.parameters != before.parameters[:position] + before.parameters[position + 1:]
        ):
            return ChangeDiagnostic(
                "operation_signature_mismatch",
                "目标签名必须只删除指定参数，其余参数及签名信息保持不变。",
            )
        return None

    def describe(self, target_symbol_id: str) -> str:
        return f"{target_symbol_id} 删除参数 {self.parameter_name}"

    def evidence_reason(self, target_symbol_id: str, reason: str) -> str:
        return reason

    def to_dict(self) -> dict[str, Any]:
        return {"change_type": self.change_type.value, "parameter_name": self.parameter_name}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RemoveParameterOperation":
        if data.get("change_type") != ChangeType.REMOVE_PARAMETER:
            raise ChangeOperationError("unsupported_change_type", "operation 类型与参数模型不一致。")
        if set(data) != {"change_type", "parameter_name"}:
            raise ChangeOperationError("invalid_operation_payload", "删除操作仅接受 change_type 和 parameter_name。")
        return cls(data["parameter_name"])


@dataclass(frozen=True)
class RenameParameterOperation:
    parameter_name: str
    new_parameter_name: str
    change_type: Literal[ChangeType.RENAME_PARAMETER] = field(
        default=ChangeType.RENAME_PARAMETER, init=False
    )
    direct_rule_id: ClassVar[str] = "parameter_renamed_breaks_keyword_call"

    def __post_init__(self) -> None:
        if not _valid_identifier(self.parameter_name):
            raise ChangeOperationError(
                "invalid_operation_payload", "parameter_name 必须是合法的 Python 参数名。"
            )
        if not _valid_identifier(self.new_parameter_name):
            raise ChangeOperationError(
                "invalid_parameter_name", "new_parameter_name 必须是合法的 Python 标识符且不能是关键字。"
            )
        # Python AST normalizes identifiers to NFKC. Use the same canonical
        # names for collision checks and later keyword binding.
        object.__setattr__(self, "parameter_name", normalize("NFKC", self.parameter_name))
        object.__setattr__(self, "new_parameter_name", normalize("NFKC", self.new_parameter_name))
        if not _valid_identifier(self.new_parameter_name):
            raise ChangeOperationError("invalid_parameter_name", "归一化后的新参数名不能是 Python 关键字。")
        if self.new_parameter_name == self.parameter_name:
            raise ChangeOperationError("parameter_name_unchanged", "新参数名必须与旧参数名不同。")

    @property
    def legacy_added_parameter(self) -> None:
        return None

    def _parameter_position(self, before: FunctionSignature) -> int:
        position = next((i for i, parameter in enumerate(before.parameters)
                         if parameter.name == self.parameter_name), None)
        if position is None:
            raise ChangeOperationError("parameter_not_found", "目标函数中没有指定的旧参数。")
        if before.parameters[position].kind not in ("positional_or_keyword", "keyword_only"):
            raise ChangeOperationError(
                "unsupported_parameter_kind",
                "当前仅支持重命名 positional_or_keyword 和 keyword_only 参数；函数体引用风险不在本轮调用兼容性分析范围内。",
            )
        if any(parameter.name == self.new_parameter_name for parameter in before.parameters):
            raise ChangeOperationError("parameter_name_conflict", "新参数名与目标函数的现有参数冲突。")
        return position

    def build_after(self, before: FunctionSignature) -> FunctionSignature:
        position = self._parameter_position(before)
        renamed = replace(before.parameters[position], name=self.new_parameter_name)
        return replace(before, parameters=(
            before.parameters[:position] + (renamed,) + before.parameters[position + 1:]
        ))

    def validate_delta(
        self, before: FunctionSignature, after: FunctionSignature
    ) -> ChangeDiagnostic | None:
        try:
            position = self._parameter_position(before)
        except ChangeOperationError as error:
            return ChangeDiagnostic(error.code, str(error))
        expected_parameters = (
            before.parameters[:position]
            + (replace(before.parameters[position], name=self.new_parameter_name),)
            + before.parameters[position + 1:]
        )
        if after != replace(before, parameters=expected_parameters):
            return ChangeDiagnostic(
                "operation_signature_mismatch",
                "目标签名必须只重命名指定参数，顺序、类型、默认值、注解及其他签名信息保持不变。",
            )
        return None

    def describe(self, target_symbol_id: str) -> str:
        return f"{target_symbol_id} 重命名参数 {self.parameter_name} → {self.new_parameter_name}"

    def evidence_reason(self, target_symbol_id: str, reason: str) -> str:
        return f"{self.describe(target_symbol_id)}。{reason}"

    def to_dict(self) -> dict[str, Any]:
        return {"change_type": self.change_type.value, "parameter_name": self.parameter_name,
                "new_parameter_name": self.new_parameter_name}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RenameParameterOperation":
        if data.get("change_type") != ChangeType.RENAME_PARAMETER:
            raise ChangeOperationError("unsupported_change_type", "operation 类型与参数模型不一致。")
        if set(data) != {"change_type", "parameter_name", "new_parameter_name"}:
            raise ChangeOperationError(
                "invalid_operation_payload", "重命名操作仅接受 change_type、parameter_name 和 new_parameter_name。"
            )
        return cls(data["parameter_name"], data["new_parameter_name"])


@dataclass(frozen=True)
class MakeParameterRequiredOperation:
    parameter_name: str
    change_type: Literal[ChangeType.MAKE_PARAMETER_REQUIRED] = field(
        default=ChangeType.MAKE_PARAMETER_REQUIRED, init=False
    )
    direct_rule_id: ClassVar[str] = "parameter_became_required_breaks_call"

    def __post_init__(self) -> None:
        if not _valid_identifier(self.parameter_name):
            raise ChangeOperationError(
                "invalid_operation_payload", "parameter_name 必须是合法的 Python 参数名。"
            )
        object.__setattr__(self, "parameter_name", normalize("NFKC", self.parameter_name))
        if not _valid_identifier(self.parameter_name):
            raise ChangeOperationError("invalid_operation_payload", "归一化后的参数名不能是 Python 关键字。")

    @property
    def legacy_added_parameter(self) -> None:
        return None

    def _parameter_position(self, before: FunctionSignature) -> int:
        position = next((i for i, parameter in enumerate(before.parameters)
                         if parameter.name == self.parameter_name), None)
        if position is None:
            raise ChangeOperationError("parameter_not_found", "目标函数中没有指定的参数。")
        parameter = before.parameters[position]
        if parameter.kind not in ("positional_only", "positional_or_keyword", "keyword_only"):
            raise ChangeOperationError("unsupported_parameter_kind", "当前不支持对 *args 或 **kwargs 移除默认值。")
        if not parameter.has_default:
            raise ChangeOperationError("parameter_already_required", "指定参数当前没有默认值，已经是必填参数。")
        return position

    def build_after(self, before: FunctionSignature) -> FunctionSignature:
        position = self._parameter_position(before)
        # has_default is authoritative: a literal default of None is represented
        # by has_default=True and default_source="None" in the source model.
        required = replace(before.parameters[position], has_default=False, default_source=None)
        after = replace(before, parameters=(
            before.parameters[:position] + (required,) + before.parameters[position + 1:]
        ))
        if not _signature_is_valid(after):
            raise ChangeOperationError(
                "invalid_after_signature", "移除默认值后签名不符合 Python 参数规则；不会重排或同时修改其他参数。"
            )
        return after

    def validate_delta(
        self, before: FunctionSignature, after: FunctionSignature
    ) -> ChangeDiagnostic | None:
        try:
            position = self._parameter_position(before)
        except ChangeOperationError as error:
            return ChangeDiagnostic(error.code, str(error))
        expected_parameters = (
            before.parameters[:position]
            + (replace(before.parameters[position], has_default=False, default_source=None),)
            + before.parameters[position + 1:]
        )
        if after != replace(before, parameters=expected_parameters):
            return ChangeDiagnostic(
                "operation_signature_mismatch",
                "目标签名必须只移除指定参数的默认值，名称、顺序、类型、注解及其他签名信息保持不变。",
            )
        if not _signature_is_valid(after):
            return ChangeDiagnostic("invalid_after_signature", "移除默认值后签名不符合 Python 参数规则。")
        return None

    def describe(self, target_symbol_id: str) -> str:
        return f"{target_symbol_id} 参数 {self.parameter_name} 从可选变为必填（移除原有默认值）"

    def evidence_reason(self, target_symbol_id: str, reason: str) -> str:
        return f"{self.describe(target_symbol_id)}。{reason}"

    def to_dict(self) -> dict[str, Any]:
        return {"change_type": self.change_type.value, "parameter_name": self.parameter_name}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MakeParameterRequiredOperation":
        if data.get("change_type") != ChangeType.MAKE_PARAMETER_REQUIRED:
            raise ChangeOperationError("unsupported_change_type", "operation 类型与参数模型不一致。")
        if set(data) != {"change_type", "parameter_name"}:
            raise ChangeOperationError(
                "invalid_operation_payload", "必填化操作仅接受 change_type 和 parameter_name。"
            )
        return cls(data["parameter_name"])


# Extend this union and read-only registry only for approved concrete operations.
ChangeOperation: TypeAlias = (
    AddRequiredParameterOperation | RemoveParameterOperation
    | RenameParameterOperation | MakeParameterRequiredOperation
)
_OPERATION_TYPES = MappingProxyType({
    ChangeType.ADD_REQUIRED_PARAMETER: AddRequiredParameterOperation,
    ChangeType.REMOVE_PARAMETER: RemoveParameterOperation,
    ChangeType.RENAME_PARAMETER: RenameParameterOperation,
    ChangeType.MAKE_PARAMETER_REQUIRED: MakeParameterRequiredOperation,
})


def operation_from_dict(data: object) -> ChangeOperation:
    if not isinstance(data, dict):
        raise ChangeOperationError("invalid_operation_payload", "operation 必须是 JSON 对象。")
    tag = data.get("change_type")
    if not isinstance(tag, str) or tag not in _OPERATION_TYPES:
        raise ChangeOperationError("unsupported_change_type", "operation 的变更类型尚未注册。")
    return _OPERATION_TYPES[tag].from_dict(data)


@dataclass(frozen=True)
class ChangeSpec:
    # Preserve the existing five positional/keyword constructor arguments.
    # Legacy intent fields are immutable compatibility views checked against
    # operation; before/after alone are the signatures assessed by the engine.
    change_type: ChangeType | str
    target_symbol_id: str
    before: FunctionSignature
    after: FunctionSignature
    added_parameter: AddedParameter | None = None
    operation: ChangeOperation | None = None

    def __post_init__(self) -> None:
        operation = self.operation
        if operation is None:
            if self.change_type == ChangeType.ADD_REQUIRED_PARAMETER and self.added_parameter is not None:
                operation = AddRequiredParameterOperation(self.added_parameter)
                object.__setattr__(self, "operation", operation)
        else:
            if type(operation) not in _OPERATION_TYPES.values():
                raise ChangeOperationError("unsupported_change_type", "operation 类型尚未注册。")
            if self.change_type != operation.change_type or (
                self.added_parameter is not None and self.added_parameter != operation.legacy_added_parameter
            ):
                raise ChangeOperationError("operation_mismatch", "旧声明字段与 operation 不一致。")
            object.__setattr__(self, "added_parameter", operation.legacy_added_parameter)

    @property
    def before_signature(self) -> FunctionSignature:
        return self.before

    @property
    def after_signature(self) -> FunctionSignature:
        return self.after

    @classmethod
    def from_operation(
        cls, target_symbol_id: str, before: FunctionSignature, operation: ChangeOperation
    ) -> "ChangeSpec":
        if type(operation) not in _OPERATION_TYPES.values():
            raise ChangeOperationError("unsupported_change_type", "operation 类型尚未注册。")
        return cls(operation.change_type, target_symbol_id, before,
                   operation.build_after(before), operation=operation)

    def describe(self) -> str:
        if self.operation is not None:
            return self.operation.describe(self.target_symbol_id)
        return f"{self.target_symbol_id} 函数签名变更（{self.change_type}）"

    def to_dict(self, *, include_operation: bool = True) -> dict[str, Any]:
        """Keep legacy add JSON intact; other operations must retain their intent."""
        def signature_data(signature: FunctionSignature) -> dict[str, Any]:
            data = asdict(signature)
            data["parameters"] = [asdict(parameter) for parameter in signature.parameters]
            return data
        data = {
            "change_type": self.change_type.value if isinstance(self.change_type, ChangeType) else self.change_type,
            "target_symbol_id": self.target_symbol_id,
            "before": signature_data(self.before), "after": signature_data(self.after),
            "added_parameter": asdict(self.added_parameter) if self.added_parameter is not None else None,
        }
        if self.operation is not None and (
            include_operation or self.operation.legacy_added_parameter is None
        ):
            data["operation"] = self.operation.to_dict()
        return data


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
    if spec.change_type not in _OPERATION_TYPES:
        return _failure(None, "unsupported_change_type", "变更类型尚未注册。")
    if spec.operation is None:
        return _failure(None, "invalid_operation_payload", "ChangeSpec 缺少 operation 参数。")
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
    if diagnostic := spec.operation.validate_delta(current, spec.after):
        return _failure(current, diagnostic.code, diagnostic.message)
    return ChangeValidationResult(True, current, ())
