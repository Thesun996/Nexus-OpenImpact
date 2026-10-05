"""Small explicit dispatch boundary; legacy function loaders remain unchanged."""

import json

from openimpact.api_change import ChangeConfigError


def read_cli_domain(path) -> tuple[str, dict]:
    # Keep the frozen CLI loader's diagnostics for unreadable/invalid legacy
    # documents. It will raise; this fallback does not manufacture a valid spec.
    try:
        source = path.read_text(encoding="utf-8-sig")
        json.loads(source)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return "function", {}
    return parse_domain_config(source)


def parse_domain_config(source: str) -> tuple[str, dict]:
    try:
        config = json.loads(source)
    except json.JSONDecodeError as error:
        raise ChangeConfigError("invalid_change_json", "change 必须是有效 JSON。") from error
    if not isinstance(config, dict):
        raise ChangeConfigError("invalid_change_config", "change 必须是 JSON 对象。")
    domain = config.get("change_domain", "function")
    if not isinstance(domain, str) or domain not in {"function", "module", "symbol"}:
        raise ChangeConfigError("unsupported_change_domain", "仅支持 function、module 或 symbol 领域。")
    if "change_domain" in config:
        def unique_keys(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ChangeConfigError("invalid_change_config", "模块配置不能包含重复 JSON 字段。")
                result[key] = value
            return result
        config = json.loads(source, object_pairs_hook=unique_keys)
    return domain, config
