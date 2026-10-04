"""Validated module intent and a virtual layout; never mutates project files."""

from dataclasses import asdict, dataclass
from typing import Literal

from openimpact.analysis.module_facts import ModuleDescriptor, ModuleInventory, name_problem, normalized_name


class ModuleChangeError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class RenameModuleOperation:
    new_module_name: str
    change_type: Literal["rename_module"] = "rename_module"

    def __post_init__(self):
        if self.change_type != "rename_module" or name_problem(self.new_module_name):
            raise ModuleChangeError(name_problem(self.new_module_name) or "invalid_operation", "新模块名必须是受支持的规范 Python 名称，不包含路径或扩展名。")


@dataclass(frozen=True)
class RemoveModuleOperation:
    change_type: Literal["remove_module"] = "remove_module"

    def __post_init__(self):
        if self.change_type != "remove_module":
            raise ModuleChangeError("invalid_operation", "模块删除操作类型无效。")


@dataclass(frozen=True)
class ModuleChangeSpec:
    target_module_id: str
    before: ModuleDescriptor
    operation: RenameModuleOperation | RemoveModuleOperation
    change_domain: Literal["module"] = "module"

    def __post_init__(self):
        if self.change_domain != "module" or not isinstance(self.operation, (RenameModuleOperation, RemoveModuleOperation)):
            raise ModuleChangeError("invalid_module_change", "模块变更必须使用模块领域的操作。")
        if self.target_module_id != self.before.module_id:
            raise ModuleChangeError("target_mismatch", "模块目标与原始模块事实不一致。")

    @property
    def change_type(self):
        return self.operation.change_type

    def to_dict(self, **_kwargs):
        after = None
        if isinstance(self.operation, RenameModuleOperation):
            after = {"module_id": self.operation.new_module_name, "file": f"{self.operation.new_module_name}.py"}
        return {"change_domain": "module", "change_type": self.change_type,
                "target_module_id": self.target_module_id, "operation": asdict(self.operation),
                "before": asdict(self.before), "after": after,
                "analysis_scope": "project_root_static", "modifies_source": False}


@dataclass(frozen=True)
class VirtualModuleLayout:
    modules: tuple[tuple[str, ModuleDescriptor], ...]
    removed_module_id: str

    def get(self, module_id: str):
        return next((descriptor for name, descriptor in self.modules if name == module_id), None)


def validate_module_change(inventory: ModuleInventory, spec: ModuleChangeSpec) -> None:
    target = inventory.get(spec.target_module_id)
    if target is None:
        raise ModuleChangeError("module_not_found", "项目内没有唯一的目标模块。")
    if not target.selectable:
        raise ModuleChangeError(target.reason or "unsupported_module", "目标不属于可分析的根目录普通 Python 模块。")
    if target != spec.before:
        raise ModuleChangeError("module_snapshot_mismatch", "目标模块源码快照已变化。")
    if isinstance(spec.operation, RenameModuleOperation):
        new = spec.operation.new_module_name
        if new == target.module_id:
            raise ModuleChangeError("unchanged_module_name", "新旧模块名称必须不同。")
        if normalized_name(new) == normalized_name(target.module_id):
            raise ModuleChangeError("module_name_conflict", "不支持仅大小写变化或等价名称。")
        if normalized_name(new) in {normalized_name(name) for name in inventory.occupied_names}:
            raise ModuleChangeError("module_name_conflict", "新模块名与项目内文件或目录冲突。")


def build_module_change(inventory: ModuleInventory, config: dict) -> ModuleChangeSpec:
    if not isinstance(config, dict) or config.get("change_domain") != "module":
        raise ModuleChangeError("invalid_module_change", "必须明确选择 module 领域。")
    kind = config.get("change_type")
    keys = {"change_domain", "change_type", "target_module_id"}
    if kind == "rename_module":
        keys.add("new_module_name")
    elif kind != "remove_module":
        raise ModuleChangeError("unsupported_module_change", "仅支持 rename_module 和 remove_module。")
    if set(config) != keys or not isinstance(config.get("target_module_id"), str):
        raise ModuleChangeError("invalid_module_change", "模块变更字段缺失或包含不支持的字段。")
    target = inventory.get(config["target_module_id"])
    if target is None:
        raise ModuleChangeError("module_not_found", "项目内没有唯一的目标模块。")
    operation = RenameModuleOperation(config["new_module_name"]) if kind == "rename_module" else RemoveModuleOperation()
    spec = ModuleChangeSpec(target.module_id, target, operation)
    validate_module_change(inventory, spec)
    return spec


def project_module_layout(inventory: ModuleInventory, spec: ModuleChangeSpec) -> VirtualModuleLayout:
    validate_module_change(inventory, spec)
    mapping = [(module.module_id, module) for module in inventory.modules if module.module_id != spec.target_module_id]
    if isinstance(spec.operation, RenameModuleOperation):
        mapping.append((spec.operation.new_module_name, spec.before))
    return VirtualModuleLayout(tuple(sorted(mapping, key=lambda item: item[0])), spec.target_module_id)
