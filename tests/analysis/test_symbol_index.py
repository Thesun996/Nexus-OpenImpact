"""Project-level symbol identity and explicit import binding tests."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from openimpact.analysis.symbol_index import SymbolIndex


class SymbolIndexTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name) / "project"
        self.root.mkdir()

    def source(self, relative_path: str, contents: str) -> None:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")

    def build(self) -> SymbolIndex:
        return SymbolIndex(self.root).build()

    def test_single_file_registers_stable_module_level_symbol(self):
        self.source("utils.py", "def format_date(date):\n    return date\n")
        index = self.build()
        symbol = index.symbols["utils.format_date"]
        self.assertEqual(symbol.symbol_id, "utils.format_date")
        self.assertEqual(symbol.module, "utils")
        self.assertEqual(symbol.qualified_name, "format_date")
        self.assertEqual(symbol.file, Path("utils.py"))
        self.assertEqual(symbol.definition.lineno, 1)
        self.assertEqual(set(self.build().symbols), {"utils.format_date"})

    def test_same_named_functions_in_different_modules_remain_distinct(self):
        self.source("a.py", "def process():\n    pass\n")
        self.source("b.py", "def process():\n    pass\n")
        self.source("report.py", "from a import process as process_a\nfrom b import process as process_b\n")
        index = self.build()
        self.assertEqual(set(index.symbols), {"a.process", "b.process"})
        self.assertNotEqual(index.symbols["a.process"].file, index.symbols["b.process"].file)
        self.assertEqual(index.bindings["report"]["process_a"].target_symbol_id, "a.process")
        self.assertEqual(index.bindings["report"]["process_b"].target_symbol_id, "b.process")

    def test_from_import_and_alias_bind_to_internal_function(self):
        self.source("utils.py", "def format_date(date):\n    pass\n")
        self.source(
            "report.py",
            "from utils import format_date\nfrom utils import format_date as fd\n",
        )
        bindings = self.build().bindings["report"]
        self.assertEqual(bindings["format_date"].target_symbol_id, "utils.format_date")
        self.assertEqual(bindings["fd"].target_symbol_id, "utils.format_date")
        self.assertEqual(bindings["fd"].kind, "function")
        self.assertEqual(bindings["fd"].status, "resolved")

    def test_import_module_and_alias_bind_to_internal_module(self):
        self.source("utils.py", "def format_date(date):\n    pass\n")
        self.source("report.py", "import utils\nimport utils as u\n")
        bindings = self.build().bindings["report"]
        for name in ("utils", "u"):
            self.assertEqual(bindings[name].kind, "module")
            self.assertEqual(bindings[name].target_module, "utils")
            self.assertIsNone(bindings[name].target_symbol_id)
            self.assertEqual(bindings[name].status, "resolved")

    def test_missing_internal_function_is_unresolved(self):
        self.source("utils.py", "def existing():\n    pass\n")
        self.source("report.py", "from utils import absent\n")
        binding = self.build().bindings["report"]["absent"]
        self.assertEqual(binding.status, "unresolved")
        self.assertEqual(binding.reason, "name_not_in_project_module")
        self.assertIsNone(binding.target_symbol_id)

    def test_external_imports_never_become_internal_function_symbols(self):
        self.source("report.py", "import json\nfrom pathlib import Path\n")
        index = self.build()
        self.assertEqual(set(index.symbols), set())
        self.assertEqual(index.bindings["report"]["json"].status, "unresolved")
        self.assertEqual(index.bindings["report"]["Path"].status, "unresolved")
        self.assertIsNone(index.bindings["report"]["Path"].target_symbol_id)

    def test_nested_package_module_name_comes_from_relative_path(self):
        self.source("pkg/__init__.py", "def top():\n    pass\n")
        self.source("pkg/helpers.py", "def helper():\n    pass\n")
        self.source("report.py", "from pkg.helpers import helper as h\n")
        index = self.build()
        self.assertEqual(index.modules["pkg"], Path("pkg/__init__.py"))
        self.assertEqual(index.modules["pkg.helpers"], Path("pkg/helpers.py"))
        self.assertEqual(index.bindings["report"]["h"].target_symbol_id, "pkg.helpers.helper")

    def test_relative_import_and_wildcard_are_unresolved(self):
        self.source("pkg/__init__.py", "")
        self.source("pkg/utils.py", "def f():\n    pass\n")
        self.source("pkg/report.py", "from .utils import f\nfrom pkg.utils import *\n")
        bindings = self.build().bindings["pkg.report"]
        self.assertEqual(bindings["f"].reason, "relative_import_unsupported")
        self.assertEqual(bindings["*"].reason, "wildcard_import_unsupported")

    def test_parse_error_does_not_register_symbol_or_resolve_import(self):
        self.source("utils.py", "def broken(:\n    pass\n")
        self.source("report.py", "from utils import broken\n")
        index = self.build()
        self.assertNotIn("utils.broken", index.symbols)
        self.assertEqual(index.parse_diagnostics[Path("utils.py")][0].kind, "syntax_error")
        self.assertEqual(index.bindings["report"]["broken"].status, "unresolved")

    def test_ambiguous_module_paths_are_not_assigned_one_identity(self):
        self.source("pkg.py", "def f():\n    pass\n")
        self.source("pkg/__init__.py", "def f():\n    pass\n")
        self.source("report.py", "from pkg import f\n")
        index = self.build()
        self.assertIn("pkg", index.ambiguous_modules)
        self.assertNotIn("pkg.f", index.symbols)
        self.assertEqual(index.bindings["report"]["f"].reason, "ambiguous_project_module")


if __name__ == "__main__":
    unittest.main()
