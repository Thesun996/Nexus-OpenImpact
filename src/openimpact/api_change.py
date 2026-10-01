"""Translate the small HTTP change form into an existing Core ChangeSpec."""

import json
from typing import Any

from openimpact.analysis.change_spec import AddedParameter, ChangeSpec, FunctionSignature
from openimpact.analysis.models import Parameter
from openimpact.analysis.symbol_index import SymbolIndex

_ADDED_KINDS = {"positional_only", "positional_or_keyword", "keyword_only"}
_ORDER = {
    "positional_only": 0,
    "positional_or_keyword": 1,
    "var_positional": 2,
    "keyword_only": 3,
    "var_keyword": 4,
}


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
    if set(config) - {"target_symbol_id", "added_parameter", "insert_before"}:
        raise ChangeConfigError("invalid_change_config", "change 包含不支持的字段。")
    target = config.get("target_symbol_id")
    added = config.get("added_parameter")
    if not isinstance(target, str) or not target:
        raise ChangeConfigError("invalid_change_config", "target_symbol_id 必须是非空字符串。")
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
    added = config["added_parameter"]
    kind = added["kind"]
    insert_before = config.get("insert_before")
    if insert_before is None:
        position = next(
            (i for i, parameter in enumerate(before.parameters)
             if _ORDER[parameter.kind] > _ORDER[kind]),
            len(before.parameters),
        )
    else:
        position = next(
            (i for i, parameter in enumerate(before.parameters)
             if parameter.name == insert_before),
            None,
        )
        if position is None:
            raise ChangeConfigError("insert_before_not_found", "insert_before 未指向现有参数。")
    new_parameter = Parameter(added["name"], kind, False)
    parameters = before.parameters[:position] + (new_parameter,) + before.parameters[position:]
    after = FunctionSignature(before.name, parameters, before.is_async, before.return_annotation_source)
    return ChangeSpec(
        "add_required_parameter", target, before, after,
        AddedParameter(added["name"], kind, True),
    )
