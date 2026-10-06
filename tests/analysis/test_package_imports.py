"""Ordinary package binding, explicit roots, and conservative failure boundaries."""

from pathlib import Path

import pytest

from openimpact.analysis.symbol_index import SymbolIndex
from openimpact.analysis.call_graph import CallGraph
from openimpact.analysis.pipeline import analyze_project
from openimpact.analysis.report import build_report
from openimpact.api_change import build_change_spec
from openimpact.repository.layout import AnalysisRootError


def write(root, **sources):
    for name, content in sources.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


@pytest.fixture
def package(tmp_path):
    write(tmp_path, **{
        "src/pkg/__init__.py": "",
        "src/pkg/utils.py": "def f(a):\n    return a\n",
        "src/pkg/report.py": "from .utils import f as alias\ndef report():\n    return alias(1)\n",
        "src/pkg/dashboard.py": "from .report import report\ndef dashboard():\n    return report()\n",
        "src/pkg/page.py": "from .dashboard import dashboard\ndef page():\n    return dashboard()\n",
        "tests/test_report.py": "from pkg.utils import f\ndef test_call():\n    return f(1)\n",
    })
    return tmp_path


def test_explicit_root_keeps_source_paths_and_binds_outside_tests(package):
    default = SymbolIndex(package).build()
    assert "src.pkg.utils.f" in default.symbols  # Legacy default is unchanged.
    index = SymbolIndex(package, analysis_root="src").build()
    assert index.symbols["pkg.utils.f"].file == Path("src/pkg/utils.py")
    assert index.bindings["tests.test_report"]["f"].target_symbol_id == "pkg.utils.f"
    assert index.bindings["pkg.report"]["alias"].target_symbol_id == "pkg.utils.f"
    assert index.bindings["pkg.report"]["alias"].source_file == Path("src/pkg/report.py")


@pytest.mark.parametrize("statement,local", [
    ("from .utils import f", "f"),
    ("from .utils import f as run", "run"),
    ("from . import utils", "utils"),
    ("from . import utils as u", "u"),
])
def test_relative_function_and_module_aliases(package, statement, local):
    (package / "src/pkg/other.py").write_text(statement, encoding="utf-8")
    index = SymbolIndex(package, analysis_root="src").build()
    binding = index.bindings["pkg.other"][local]
    assert binding.status == "resolved"
    assert binding.target_module == "pkg.utils"


def test_parent_import_and_package_initializer_context(package):
    write(package, **{
        "src/pkg/sub/__init__.py": "from ..utils import f as exported\n",
        "src/pkg/sub/report.py": "from ..utils import f\ndef report():\n    return f(1)\n",
    })
    index = SymbolIndex(package, analysis_root="src").build()
    assert index.bindings["pkg.sub"]["exported"].target_symbol_id == "pkg.utils.f"
    assert index.bindings["pkg.sub.report"]["f"].target_symbol_id == "pkg.utils.f"
    # Registering this import fact does not implement re-export traversal.
    write(package, **{"other.py": "from pkg.sub import exported\n"})
    assert SymbolIndex(package, analysis_root="src").build().bindings["other"]["exported"].status == "unresolved"


@pytest.mark.parametrize("source,statement,reason", [
    ("plain.py", "from .utils import f", "relative_import_without_package"),
    ("src/pkg/other.py", "from ..utils import f", "relative_import_beyond_package"),
    ("src/pkg/other.py", "from .missing import f", "module_not_in_project"),
    ("src/pkg/other.py", "from .utils import absent", "name_not_in_project_module"),
    ("src/pkg/other.py", "from .utils import *", "wildcard_import_unsupported"),
])
def test_unresolved_relative_cases_are_not_guessed(package, source, statement, reason):
    write(package, **{source: statement})
    index = SymbolIndex(package, analysis_root="src").build()
    binding = next(iter(index.bindings[index.module_name(Path(source))].values()))
    assert binding.status == "unresolved" and binding.reason == reason


def test_namespace_package_and_modified_package_path_are_unresolved(package):
    write(package, **{"src/pkg/nested/caller.py": "from ..utils import f\n"})
    index = SymbolIndex(package, analysis_root="src").build()
    assert index.bindings["pkg.nested.caller"]["f"].reason == "namespace_package_unsupported"
    (package / "src/pkg/__init__.py").write_text("__path__ = []\n", encoding="utf-8")
    index = SymbolIndex(package, analysis_root="src").build()
    assert index.bindings["pkg.report"]["alias"].reason == "package_path_rebound"
    assert index.bindings["tests.test_report"]["f"].reason == "package_path_rebound"


def test_parse_failed_initializer_prevents_certain_binding(package):
    (package / "src/pkg/__init__.py").write_text("def broken(:\n", encoding="utf-8")
    index = SymbolIndex(package, analysis_root="src").build()
    assert index.bindings["pkg.report"]["alias"].reason == "module_parse_failed"


def test_two_import_roots_never_choose_a_conflicting_definition(package):
    write(package, **{"pkg/__init__.py": "", "pkg/utils.py": "def f(a):\n    return a\n"})
    index = SymbolIndex(package, analysis_root="src").build()
    assert "pkg" in index.ambiguous_modules and "pkg.utils" in index.ambiguous_modules
    assert index.bindings["pkg.report"]["alias"].status == "unresolved"
    assert "pkg.utils.f" not in index.symbols


def test_matching_function_names_in_other_package_never_cross_bind(package):
    write(package, **{"src/other/__init__.py": "", "src/other/utils.py": "def f(a):\n    return a\n",
                     "src/other/caller.py": "from .utils import f\ndef caller():\n    return f(1)\n"})
    graph = CallGraph(SymbolIndex(package, analysis_root="src").build()).build()
    edges = {(e.caller_symbol_id, e.callee_symbol_id) for e in graph.edges}
    assert ("pkg.report.report", "pkg.utils.f") in edges
    assert ("other.caller.caller", "other.utils.f") in edges
    assert ("other.caller.caller", "pkg.utils.f") not in edges


def test_unchanged_impact_algorithms_trace_package_chain_and_real_evidence(package):
    index = SymbolIndex(package, analysis_root="src").build()
    spec = build_change_spec(index, {"target_symbol_id": "pkg.utils.f",
        "added_parameter": {"name": "strict", "kind": "keyword_only"}})
    before = {p: p.read_bytes() for p in package.rglob("*.py")}
    report = build_report(analyze_project(package, spec, analysis_root="src"))
    assert report["summary"]["direct_impact_count"] == 2  # Library + test function.
    assert report["summary"]["indirect_1hop_count"] == 1
    assert report["summary"]["indirect_2hop_count"] == 1
    assert report["coverage"]["status"] == "complete"
    assert report["analysis_layout"]["analysis_root"] == "src"
    assert {e["location"]["file"] for e in report["evidences"]} == {
        "src/pkg/report.py", "tests/test_report.py", "src/pkg/dashboard.py", "src/pkg/page.py"}
    assert before == {p: p.read_bytes() for p in package.rglob("*.py")}


@pytest.mark.parametrize("root", ["", "..", "../src", "/src", "C:/src", "src/../src",
                                  "src\\pkg", "src//pkg", "missing", "src/pkg", "NUL"])
def test_invalid_root_is_rejected_before_reading_outside_project(package, root):
    with pytest.raises(AnalysisRootError):
        SymbolIndex(package, analysis_root=root)


def test_symlink_root_is_not_followed(package, tmp_path):
    linked = package / "linked"
    try:
        linked.symlink_to(package / "src", target_is_directory=True)
    except OSError:
        pytest.skip("Host does not permit directory symlinks")
    with pytest.raises(AnalysisRootError):
        SymbolIndex(package, analysis_root="linked")


def test_absolute_package_alias_cannot_bind_through_a_normal_file(package):
    write(package, **{"src/pkg.py": "", "src/pkg/caller.py": "import pkg.utils as u\ndef call():\n    return u.f(1)\n"})
    (package / "src/pkg/__init__.py").unlink()
    index = SymbolIndex(package, analysis_root="src").build()
    assert index.bindings["pkg.caller"]["u"].reason == "parent_module_is_not_package"
    assert not any(e.caller_symbol_id == "pkg.caller.call" for e in CallGraph(index).build().edges)


def test_package_itself_with_modified_search_path_is_not_bound(package):
    write(package, **{"src/pkg/__init__.py": "__path__ = []\ndef f(a):\n    return a\n",
                     "consumer.py": "from pkg import f\ndef call():\n    return f(1)\n"})
    index = SymbolIndex(package, analysis_root="src").build()
    assert index.bindings["consumer"]["f"].reason == "package_path_rebound"


@pytest.mark.parametrize("context", ["__package__", "__spec__"])
def test_rebound_package_context_cannot_produce_a_relative_binding(package, context):
    write(package, **{"src/pkg/report.py": f"{context} = None\nfrom .utils import f\ndef report():\n    return f(1)\n"})
    index = SymbolIndex(package, analysis_root="src").build()
    assert index.bindings["pkg.report"]["f"].reason == "package_context_rebound"


@pytest.mark.parametrize("initializer", ["utils = 1\n", "from other import utils\n"])
def test_package_member_cannot_be_guessed_to_be_a_matching_child_module(package, initializer):
    write(package, **{"src/pkg/__init__.py": initializer,
                     "consumer.py": "from pkg import utils as u\ndef call():\n    return u.f(1)\n"})
    index = SymbolIndex(package, analysis_root="src").build()
    assert index.bindings["consumer"]["u"].reason == "package_member_not_proven"
    assert not any(e.caller_symbol_id == "consumer.call" for e in CallGraph(index).build().edges)


def test_named_and_lambda_scopes_gain_evidence_without_inventing_callback_edges(tmp_path):
    write(tmp_path, **{"module.py": "def target():\n    return 1\n"
        "class Example:\n    def method(self):\n        return target()\n"
        "def outer():\n    def nested():\n        return target()\n    return 1\n"
        "callback = lambda: target()\n"})
    index = SymbolIndex(tmp_path).build()
    spec = build_change_spec(index, {"target_symbol_id": "module.target",
        "added_parameter": {"name": "strict", "kind": "keyword_only"}})
    report = build_report(analyze_project(tmp_path, spec))
    assert report["summary"]["direct_impact_count"] == 3
    assert report["coverage"]["status"] == "complete"
    assert not report["diagnostics"].get("unsupported_scopes")
    assert {f['caller_symbol_id'] for f in report['direct_impacts']} == {
        'module.Example.method', 'module.outer.<locals>.nested', 'module.<lambda@10:11>'}
    assert not report['indirect_impacts']
    assert len(report['evidences']) == 3
    assert all(e['status'] == 'available' for e in report['evidences'])
