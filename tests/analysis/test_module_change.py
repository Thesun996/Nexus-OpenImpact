from pathlib import Path
import hashlib
import json
from dataclasses import FrozenInstanceError

import pytest

from openimpact.analysis.module_change import (
    ModuleChangeError, build_module_change, project_module_layout, validate_module_change,
)
from openimpact.analysis.module_facts import ModuleInventory
from openimpact.analysis.symbol_index import SymbolIndex


def inventory(tmp_path, files=None):
    for name, text in (files or {"utils.py": "def format_date(x):\n    return x\n"}).items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return ModuleInventory.from_index(SymbolIndex(tmp_path).build())


def config(kind="rename_module", target="utils", new="formatting"):
    result = {"change_domain": "module", "change_type": kind, "target_module_id": target}
    if kind == "rename_module":
        result["new_module_name"] = new
    return result


@pytest.mark.parametrize("kind", ["rename_module", "remove_module"])
def test_immutable_roundtrip_virtual_only(tmp_path, kind):
    data = inventory(tmp_path)
    original = (tmp_path / "utils.py").read_bytes()
    spec = build_module_change(data, config(kind))
    assert build_module_change(data, json.loads(json.dumps(config(kind)))) == spec
    with pytest.raises(FrozenInstanceError):
        spec.target_module_id = "other"
    projection = project_module_layout(data, spec)
    assert projection.get("utils") is None
    assert bool(projection.get("formatting")) == (kind == "rename_module")
    assert spec.before.source_hash == hashlib.sha256(original).hexdigest()
    assert spec.to_dict()["change_domain"] == "module"
    assert (tmp_path / "utils.py").read_bytes() == original
    assert not (tmp_path / "formatting.py").exists()


@pytest.mark.parametrize("new", ["../escape", "/root", "E:\\escape", "formatting.py", "pkg.utils", "", "class", "con", "ｆｏｏ", "sys", "__init__", None, 42])
def test_reject_names(tmp_path, new):
    with pytest.raises(ModuleChangeError):
        build_module_change(inventory(tmp_path), config(new=new))


@pytest.mark.parametrize("new", ["utils", "UTILS", "formatting", "folder"])
def test_conflicts(tmp_path, new):
    data = inventory(tmp_path, {"utils.py": "", "formatting.py": "", "folder/helper.py": ""})
    with pytest.raises(ModuleChangeError):
        build_module_change(data, config(new=new))


def test_uppercase_extension_still_occupies_portable_destination(tmp_path):
    data = inventory(tmp_path, {"utils.py": "", "Formatting.PY": "# not analyzed"})
    assert {item.file for item in data.modules} == {"utils.py"}
    with pytest.raises(ModuleChangeError) as error:
        build_module_change(data, config())
    assert error.value.code == "module_name_conflict"


@pytest.mark.parametrize("target", ["missing", "pkg", "pkg.helper", "__main__", "json", "bad"])
def test_target_boundaries(tmp_path, target):
    data = inventory(tmp_path, {"utils.py": "", "pkg/__init__.py": "", "pkg/helper.py": "",
                                "__main__.py": "", "json.py": "", "bad.py": "def broken(:"})
    with pytest.raises(ModuleChangeError):
        build_module_change(data, config(target=target))


def test_source_changed_and_extra_keys(tmp_path):
    data = inventory(tmp_path)
    spec = build_module_change(data, config())
    (tmp_path / "utils.py").write_text("# changed", encoding="utf-8")
    with pytest.raises(ModuleChangeError, match="快照"):
        validate_module_change(ModuleInventory.from_index(SymbolIndex(tmp_path).build()), spec)
    with pytest.raises(ModuleChangeError):
        build_module_change(data, {**config(), "server_path": "/tmp"})


def test_case_conflict_and_ambiguous_module(tmp_path):
    data = inventory(tmp_path, {"pkg.py": "", "pkg/__init__.py": "", "utils.py": ""})
    assert not data.get("pkg")
    assert all(not item.selectable for item in data.modules if item.module_id == "pkg")
    extra = ModuleInventory.from_index(SymbolIndex(tmp_path).build(), ("FORMATTING",))
    with pytest.raises(ModuleChangeError):
        build_module_change(extra, config())


@pytest.mark.parametrize("name,code", [("x" * 253, "module_name_too_long"), ("界" * 85, "module_name_too_long"), ("__INIT__", "special_module_unsupported"), ("OS", "standard_library_name_collision")])
def test_portable_virtual_name_limits(name, code):
    from openimpact.analysis.module_facts import name_problem
    assert name_problem(name) == code


def test_unreadable_inventory_does_not_break_other_candidates(tmp_path, monkeypatch):
    from openimpact.analysis.symbol_index import SymbolIndex
    (tmp_path / "good.py").write_text("x=1", encoding="utf-8")
    (tmp_path / "bad.py").write_text("x=1", encoding="utf-8")
    index = SymbolIndex(tmp_path).build()
    original = Path.read_bytes
    def unreadable(path):
        if path.name == "bad.py":
            raise PermissionError("private path must not leak")
        return original(path)
    monkeypatch.setattr(Path, "read_bytes", unreadable)
    inventory = ModuleInventory.from_index(index)
    assert inventory.get("good").selectable
    assert not inventory.get("bad").selectable
    assert inventory.get("bad").reason == "module_source_unavailable"
    assert "private path" not in str(inventory.to_dict())
