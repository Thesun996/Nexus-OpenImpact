"""Load the V1 structured ChangeSpec JSON format."""

import json
from pathlib import Path
from typing import Any

from openimpact.analysis.change_spec import (
    AddedParameter,
    ChangeSpec,
    FunctionSignature,
)
from openimpact.analysis.models import Parameter

_PARAMETER_KINDS = {
    "positional_only", "positional_or_keyword", "keyword_only",
    "var_positional", "var_keyword",
}
_ADDED_KINDS = {"positional_only", "positional_or_keyword", "keyword_only"}


class ChangeFileError(ValueError):
    """The change file cannot be read as a structured V1 ChangeSpec."""


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ChangeFileError(f"{label} 必须是 JSON 对象。")
    return value


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ChangeFileError(f"{label} 必须是非空字符串。")
    return value


def _optional_string(value: Any, label: str) -> str | None:
    if value is not None and not isinstance(value, str):
        raise ChangeFileError(f"{label} 必须是字符串或 null。")
    return value


def _bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ChangeFileError(f"{label} 必须是布尔值。")
    return value


def _parameter(value: Any, label: str) -> Parameter:
    data = _object(value, label)
    name = _string(data.get("name"), f"{label}.name")
    kind = _string(data.get("kind"), f"{label}.kind")
    if kind not in _PARAMETER_KINDS:
        raise ChangeFileError(f"{label}.kind 不受支持：{kind}")
    has_default = _bool(data.get("has_default"), f"{label}.has_default")
    return Parameter(
        name, kind, has_default,
        _optional_string(data.get("default_source"), f"{label}.default_source"),
        _optional_string(data.get("annotation_source"), f"{label}.annotation_source"),
    )


def _signature(value: Any, label: str) -> FunctionSignature:
    data = _object(value, label)
    parameters = data.get("parameters")
    if not isinstance(parameters, list):
        raise ChangeFileError(f"{label}.parameters 必须是数组。")
    return FunctionSignature(
        _string(data.get("name"), f"{label}.name"),
        tuple(_parameter(item, f"{label}.parameters[{index}]")
              for index, item in enumerate(parameters)),
        _bool(data.get("is_async", False), f"{label}.is_async"),
        _optional_string(data.get("return_annotation_source"),
                         f"{label}.return_annotation_source"),
    )


def load_change_spec(path: str | Path) -> ChangeSpec:
    """Read JSON only; target matching and change semantics remain in validation."""
    file_path = Path(path)
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ChangeFileError(f"无法读取 ChangeSpec 文件 {file_path}: {error}") from error
    except UnicodeError as error:
        raise ChangeFileError(f"ChangeSpec 文件编码错误 {file_path}: {error}") from error
    except json.JSONDecodeError as error:
        raise ChangeFileError(
            f"ChangeSpec JSON 无效 {file_path}:{error.lineno}:{error.colno}: {error.msg}"
        ) from error
    spec = _object(data, "ChangeSpec")
    added = _object(spec.get("added_parameter"), "added_parameter")
    kind = _string(added.get("kind"), "added_parameter.kind")
    if kind not in _ADDED_KINDS:
        raise ChangeFileError(f"added_parameter.kind 不受支持：{kind}")
    return ChangeSpec(
        _string(spec.get("change_type"), "change_type"),
        _string(spec.get("target_symbol_id"), "target_symbol_id"),
        _signature(spec.get("before"), "before"),
        _signature(spec.get("after"), "after"),
        AddedParameter(
            _string(added.get("name"), "added_parameter.name"), kind,
            _bool(added.get("required"), "added_parameter.required"),
            _optional_string(added.get("annotation_source"),
                             "added_parameter.annotation_source"),
        ),
    )
