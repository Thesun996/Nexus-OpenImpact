import pytest

from openimpact.analysis.import_resolver import resolve_imports
from openimpact.analysis.module_facts import ModuleInventory
from openimpact.analysis.module_graph import ModuleDependencyGraph
from openimpact.analysis.symbol_index import SymbolIndex


def project(tmp_path, source, extras=None):
    files = {"utils.py": "def format_date(x):\n    return x\n", "report.py": source, **(extras or {})}
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    index = SymbolIndex(tmp_path).build()
    return index, ModuleInventory.from_index(index)


@pytest.mark.parametrize("source", ["import utils", "import utils as u", "from utils import format_date", "from utils import format_date as fd"])
def test_four_forms(tmp_path, source):
    index, inventory = project(tmp_path, source)
    refs = resolve_imports(index, inventory)
    assert len(refs) == 1
    assert refs[0].status == "resolved_project"
    assert refs[0].target_module_id == "utils"
    assert refs[0].syntax.source_text == source
    assert (refs[0].file, refs[0].syntax.line, refs[0].syntax.column) == ("report.py", 1, 0)
    assert resolve_imports(index, inventory) == refs
    edge = ModuleDependencyGraph.from_imports(refs).edges[0]
    assert (edge.importer_module_id, edge.target_module_id) == ("report", "utils")


def test_multiple_occurrences_do_not_use_overwritten_binding(tmp_path):
    index, inventory = project(tmp_path, "import utils as x; import utils as x\nfrom utils import format_date, format_date as fd\n")
    refs = resolve_imports(index, inventory)
    assert len(refs) == len({item.reference_id for item in refs}) == 4
    assert len(ModuleDependencyGraph.from_imports(refs + refs).edges) == 4
    assert refs[1].syntax.column > 0
    assert all(item.status == "resolved_project" for item in refs)


@pytest.mark.parametrize("source,reason", [
    ("from .utils import format_date", "relative_import_unsupported"),
    ("from pkg import utils", "unsupported_module_layout"),
    ("import pkg.utils", "package_import_unsupported"),
    ("from utils import *", "wildcard_import_unsupported"),
    ("from utils import unknown", "imported_member_not_proven"),
    ("if True:\n    import utils", "conditional_or_local_import_unsupported"),
    ("try:\n    import utils\nexcept ImportError:\n    pass", "conditional_or_local_import_unsupported"),
    ("def f():\n    import utils", "conditional_or_local_import_unsupported"),
    ("class C:\n    import utils", "conditional_or_local_import_unsupported"),
])
def test_unsupported_keeps_real_location(tmp_path, source, reason):
    index, inventory = project(tmp_path, source, {"pkg/__init__.py": "", "pkg/utils.py": ""})
    refs = [item for item in resolve_imports(index, inventory) if item.file == "report.py"]
    assert refs[0].status == "manual_review"
    assert refs[0].reason == reason
    assert refs[0].syntax.line > 0
    assert not ModuleDependencyGraph.from_imports(tuple(refs)).edges


@pytest.mark.parametrize("source", ["import importlib\nimportlib.import_module('utils')", "import importlib as il\nil.import_module('utils')", "from importlib import import_module as load\nload('utils')", "__import__('utils')", "exec('import utils')"])
def test_dynamic_facts_without_binding(tmp_path, source):
    index, inventory = project(tmp_path, source)
    diagnostics = index.parsed_modules["report"].module_diagnostics
    assert len(diagnostics) == 1
    assert diagnostics[0].line > 0
    assert not ModuleDependencyGraph.from_imports(resolve_imports(index, inventory)).edges


def test_same_name_nested_and_external_do_not_bind(tmp_path):
    index, inventory = project(tmp_path, "import other\nimport missing\nimport pkg.utils\n", {"other.py": "", "pkg/utils.py": ""})
    refs = resolve_imports(index, inventory)
    assert [(item.status, item.target_module_id) for item in refs] == [
        ("resolved_project", "other"), ("unresolved", None), ("manual_review", None)]


def test_cycle_reverse_no_dependency_and_parse_failure(tmp_path):
    index, inventory = project(tmp_path, "import utils", {"utils.py": "import report", "alone.py": "", "bad.py": "def broken(:"})
    graph = ModuleDependencyGraph.from_imports(resolve_imports(index, inventory))
    assert len(graph.edges) == 2
    assert graph.reverse()["utils"][0].importer_module_id == "report"
    assert graph.reverse()["report"][0].importer_module_id == "utils"
    assert "bad.py" in {path.as_posix() for path in index.parse_diagnostics}


def test_unknown_member_reexport_and_rebinding(tmp_path):
    index, inventory = project(tmp_path, "from utils import format_date", {"utils.py": "from other import format_date\n", "other.py": "def format_date(x):\n    return x"})
    report_reference = next(item for item in resolve_imports(index, inventory) if item.file == "report.py")
    assert report_reference.status == "manual_review"
    assert report_reference.reason == "imported_member_not_proven"
    (tmp_path / "utils.py").write_text("def format_date(x):\n    return x\nformat_date = object()", encoding="utf-8")
    rebuilt = SymbolIndex(tmp_path).build()
    assert resolve_imports(rebuilt, ModuleInventory.from_index(rebuilt))[0].status == "manual_review"
