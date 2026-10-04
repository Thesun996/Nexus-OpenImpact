"""Translate the small HTTP change form into an existing Core ChangeSpec."""

import json
from typing import Any

from openimpact.analysis.change_spec import (
    ChangeOperationError, ChangeSpec, ChangeType, FunctionSignature, operation_from_dict,
)
from openimpact.analysis.symbol_index import SymbolIndex

_ADDED_KINDS = {"positional_only", "positional_or_keyword", "keyword_only"}


class ChangeConfigError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def parse_change_config(source: str) -> dict[str, Any]:
    try:
        config = json.loads(source)
    except json.JSONDecodeError as error:
        raise ChangeConfigError("invalid_change_json", f"change 不是有效 JSON：{error.msg}") from error
    if not isinstance(config, dict):
        raise ChangeConfigError("invalid_change_config", "change 必须是 JSON 对象。")
    target = config.get("target_symbol_id")
    if not isinstance(target, str) or not target:
        raise ChangeConfigError("invalid_change_config", "target_symbol_id 必须是非空字符串。")
    change_type = config.get("change_type", ChangeType.ADD_REQUIRED_PARAMETER.value)
    if change_type == ChangeType.MAKE_PARAMETER_REQUIRED:
        if set(config) != {"target_symbol_id", "change_type", "parameter_name"}:
            raise ChangeConfigError(
                "invalid_change_config", "必填化配置仅需 target_symbol_id、change_type 和 parameter_name。"
            )
        try:
            operation_from_dict({"change_type": change_type, "parameter_name": config["parameter_name"]})
        except ChangeOperationError as error:
            raise ChangeConfigError(error.code, str(error)) from error
        return config
    if change_type == ChangeType.RENAME_PARAMETER:
        if set(config) != {"target_symbol_id", "change_type", "parameter_name", "new_parameter_name"}:
            raise ChangeConfigError(
                "invalid_change_config", "重命名配置仅需 target_symbol_id、change_type、parameter_name 和 new_parameter_name。"
            )
        try:
            operation_from_dict({key: value for key, value in config.items() if key != "target_symbol_id"})
        except ChangeOperationError as error:
            raise ChangeConfigError(error.code, str(error)) from error
        return config
    if change_type == ChangeType.REMOVE_PARAMETER:
        if set(config) != {"target_symbol_id", "change_type", "parameter_name"}:
            raise ChangeConfigError("invalid_change_config", "删除配置仅需 target_symbol_id、change_type 和 parameter_name。")
        try:
            operation_from_dict({"change_type": change_type, "parameter_name": config["parameter_name"]})
        except ChangeOperationError as error:
            raise ChangeConfigError(error.code, str(error)) from error
        return config
    if change_type != ChangeType.ADD_REQUIRED_PARAMETER:
        raise ChangeConfigError("invalid_change_config", "change_type 必须是已支持的变更类型。")
    if set(config) - {"target_symbol_id", "added_parameter", "insert_before", "change_type"}:
        raise ChangeConfigError("invalid_change_config", "change 包含不支持的字段。")
    added = config.get("added_parameter")
    if not isinstance(added, dict) or set(added) != {"name", "kind"}:
        raise ChangeConfigError("invalid_change_config", "added_parameter 仅需 name 和 kind。")
    if not isinstance(added["name"], str) or not added["name"]:
        raise ChangeConfigError("invalid_change_config", "added_parameter.name 必须是非空字符串。")
    if not isinstance(added["kind"], str) or added["kind"] not in _ADDED_KINDS:
        raise ChangeConfigError("unsupported_parameter_kind", "新增参数类型不受支持。")
    insert_before = config.get("insert_before")
    if insert_before is not None and (not isinstance(insert_before, str) or not insert_before):
        raise ChangeConfigError("invalid_change_config", "insert_before 必须是现有参数名称。")
    return config


def build_change_spec(index: SymbolIndex, config: dict[str, Any]) -> ChangeSpec:
    target = config["target_symbol_id"]
    symbol = index.symbols.get(target)
    if symbol is None:
        raise ChangeConfigError("target_not_found", "项目索引中没有这个模块级函数。")
    before = FunctionSignature.from_definition(symbol.definition)
    try:
        change_type = config.get("change_type", ChangeType.ADD_REQUIRED_PARAMETER.value)
        if change_type == ChangeType.RENAME_PARAMETER:
            payload = {"change_type": change_type, "parameter_name": config["parameter_name"],
                       "new_parameter_name": config["new_parameter_name"]}
        elif change_type in (ChangeType.REMOVE_PARAMETER, ChangeType.MAKE_PARAMETER_REQUIRED):
            payload = {"change_type": change_type, "parameter_name": config["parameter_name"]}
        else:
            payload = {
                "change_type": change_type,
                "added_parameter": {**config["added_parameter"], "required": True},
                "insert_before": config.get("insert_before"),
            }
        operation = operation_from_dict(payload)
        return ChangeSpec.from_operation(target, before, operation)
    except ChangeOperationError as error:
        raise ChangeConfigError(error.code, str(error)) from error
