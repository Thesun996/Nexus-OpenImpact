"""Only provable function-to-function calls become graph edges."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from openimpact.analysis.call_graph import CallGraph
from openimpact.analysis.symbol_index import SymbolIndex


class CallGraphTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name) / "project"
        self.root.mkdir()

    def source(self, relative_path: str, contents: str) -> None:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")

    def graph(self) -> CallGraph:
        return CallGraph(SymbolIndex(self.root).build()).build()

    def test_same_module_call_has_caller_callee_and_location(self):
        self.source("work.py", "def a():\n    return b()\n\ndef b():\n    pass\n")
        graph = self.graph()
        self.assertEqual(len(graph.edges), 1)
        edge = next(iter(graph.edges))
        self.assertEqual((edge.caller_symbol_id, edge.callee_symbol_id), ("work.a", "work.b"))
        self.assertEqual((edge.file, edge.line), (Path("work.py"), 2))
        self.assertEqual((edge.status, edge.basis), ("resolved", "same_module"))

    def test_from_import_and_alias_calls(self):
        self.source("utils.py", "def format_date(x):\n    pass\n")
        self.source(
            "report.py",
            "from utils import format_date\n"
            "from utils import format_date as fd\n"
            "def report(x):\n"
            "    format_date(x)\n"
            "    fd(x)\n",
        )
        graph = self.graph()
        self.assertEqual(
            {(edge.caller_symbol_id, edge.callee_symbol_id, edge.line, edge.basis)
             for edge in graph.edges},
            {
                ("report.report", "utils.format_date", 4, "from_import"),
                ("report.report", "utils.format_date", 5, "from_import"),
            },
        )

    def test_module_attribute_and_module_alias_calls(self):
        self.source("utils.py", "def format_date(x):\n    pass\n")
        self.source(
            "report.py",
            "import utils\nimport utils as u\n"
            "def report(x):\n"
            "    utils.format_date(x)\n"
            "    u.format_date(x)\n",
        )
        graph = self.graph()
        self.assertEqual(
            {(edge.callee_symbol_id, edge.line, edge.basis) for edge in graph.edges},
            {("utils.format_date", 4, "module_import"),
             ("utils.format_date", 5, "module_import")},
        )

    def test_same_name_in_two_modules_does_not_cross_bind(self):
        self.source("a.py", "def process():\n    pass\n")
        self.source("b.py", "def process():\n    pass\n")
        self.source(
            "report.py",
            "from a import process as run_a\nfrom b import process as run_b\n"
            "def report():\n    run_a()\n    run_b()\n",
        )
        self.assertEqual(
            {(edge.callee_symbol_id, edge.line) for edge in self.graph().edges},
            {("a.process", 4), ("b.process", 5)},
        )

    def test_missing_and_external_callees_remain_unresolved(self):
        self.source("utils.py", "def existing():\n    pass\n")
        self.source(
            "report.py",
            "import json\nfrom utils import missing\n"
            "def report():\n    missing()\n    json.loads('{}')\n    nowhere()\n",
        )
        graph = self.graph()
        self.assertEqual(graph.edges, set())
        self.assertEqual(
            {item.call.expression: item.reason for item in graph.unresolved_calls},
            {
                "missing": "import_binding_unresolved",
                "json.loads": "import_binding_unresolved",
                "nowhere": "name_not_indexed",
            },
        )

    def test_module_level_call_does_not_enter_function_graph(self):
        self.source("work.py", "def target():\n    pass\ntarget()\n")
        graph = self.graph()
        self.assertEqual(graph.edges, set())
        self.assertEqual(graph.unresolved_calls[0].reason, "module_level_call")
        self.assertIsNone(graph.unresolved_calls[0].caller_symbol_id)

    def test_cycle_stores_both_edges_without_traversal(self):
        self.source("work.py", "def a():\n    b()\ndef b():\n    a()\n")
        self.assertEqual(
            {(edge.caller_symbol_id, edge.callee_symbol_id) for edge in self.graph().edges},
            {("work.a", "work.b"), ("work.b", "work.a")},
        )

    def test_rebuilding_does_not_duplicate_call_point(self):
        self.source("work.py", "def a():\n    b()\ndef b():\n    pass\n")
        graph = CallGraph(SymbolIndex(self.root).build())
        graph.build()
        graph.build()
        self.assertEqual(len(graph.edges), 1)

    def test_distinct_call_points_on_one_line_are_preserved(self):
        self.source("work.py", "def a():\n    b(); b()\ndef b():\n    pass\n")
        graph = self.graph()
        self.assertEqual(len(graph.edges), 2)
        self.assertEqual({edge.line for edge in graph.edges}, {2})
        self.assertEqual(len({edge.col_offset for edge in graph.edges}), 2)

    def test_dynamic_attribute_chain_and_function_forwarding_stay_unresolved(self):
        self.source("utils.py", "def f():\n    pass\n")
        self.source(
            "report.py",
            "import utils\n"
            "def report(fn):\n"
            "    fn()\n"
            "    getattr(utils, 'f')()\n"
            "    utils.factory.f()\n",
        )
        graph = self.graph()
        self.assertEqual(graph.edges, set())
        reasons = {item.reason for item in graph.unresolved_calls}
        self.assertIn("local_name_shadows_target", reasons)
        self.assertIn("unsupported_callee_expression", reasons)
        self.assertIn("attribute_chain_unsupported", reasons)

    def test_local_and_module_rebinding_prevent_certain_edges(self):
        self.source(
            "work.py",
            "def target():\n    pass\n"
            "def local():\n    target = factory\n    target()\n"
            "target = replacement\n"
            "def later():\n    target()\n",
        )
        graph = self.graph()
        self.assertEqual(graph.edges, set())
        self.assertEqual(
            {item.reason for item in graph.unresolved_calls},
            {"local_name_shadows_target", "module_name_rebound"},
        )

    def test_rebound_function_in_target_module_is_unresolved(self):
        self.source("utils.py", "def target():\n    pass\ntarget = replacement\n")
        self.source(
            "report.py",
            "import utils\nfrom utils import target as direct\n"
            "def report():\n    utils.target()\n    direct()\n",
        )
        graph = self.graph()
        self.assertEqual(graph.edges, set())
        self.assertEqual(
            [item.reason for item in graph.unresolved_calls],
            ["callee_module_name_rebound", "callee_module_name_rebound"],
        )

    def test_nested_and_method_scopes_resolve_only_the_known_module_function(self):
        self.source(
            "work.py",
            "def target():\n    pass\n"
            "def outer():\n"
            "    def nested():\n        target()\n"
            "class C:\n    def method(self):\n        target()\n",
        )
        graph = self.graph()
        self.assertEqual({(e.caller_symbol_id, e.callee_symbol_id) for e in graph.edges},
            {('work.outer.<locals>.nested', 'work.target'), ('work.C.method', 'work.target')})
        self.assertEqual(set(graph.index.symbols), {'work.target', 'work.outer'})


if __name__ == "__main__":
    unittest.main()
