"""Bounded reverse propagation from definite change-caused direct calls."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from openimpact.analysis.call_graph import CallGraph
from openimpact.analysis.change_spec import (
    AddedParameter,
    ChangeSpec,
    FunctionSignature,
)
from openimpact.analysis.direct_impact import analyze_direct_impact
from openimpact.analysis.indirect_impact import propagate_indirect_impact
from openimpact.analysis.models import Parameter
from openimpact.analysis.symbol_index import SymbolIndex


class IndirectImpactTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name) / "project"
        self.root.mkdir()
        self.source("utils.py", "def format_date(date):\n    pass\n")

    def source(self, filename: str, content: str) -> None:
        path = self.root / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def analyze(self, max_depth: int = 2):
        graph = CallGraph(SymbolIndex(self.root).build()).build()
        before = FunctionSignature.from_definition(
            graph.index.symbols["utils.format_date"].definition
        )
        after = FunctionSignature(
            "format_date", (*before.parameters, Parameter("timezone", "positional_or_keyword"))
        )
        spec = ChangeSpec(
            "add_required_parameter", "utils.format_date", before, after,
            AddedParameter("timezone", "positional_or_keyword"),
        )
        direct = analyze_direct_impact(graph, spec)
        return direct, propagate_indirect_impact(graph, direct, max_depth)

    def test_chain_has_direct_one_hop_and_two_hop_with_call_evidence(self):
        self.source("report.py", "from utils import format_date\ndef report(x):\n    format_date(x)\n")
        self.source("dashboard.py", "from report import report\ndef dashboard():\n    report(1)\n")
        self.source("page.py", "from dashboard import dashboard\ndef page():\n    dashboard()\n")
        direct, indirect = self.analyze()
        self.assertEqual(direct.direct_impact_count, 1)
        self.assertEqual(direct.findings[0].assessment.caller_symbol_id, "report.report")
        by_symbol = {finding.impacted_symbol_id: finding for finding in indirect.findings}
        self.assertEqual(set(by_symbol), {"dashboard.dashboard", "page.page"})
        self.assertEqual((by_symbol["dashboard.dashboard"].impact_type,
                          by_symbol["dashboard.dashboard"].graph_distance),
                         ("indirect_1hop", 2))
        page = by_symbol["page.page"]
        self.assertEqual((page.impact_type, page.graph_distance, page.certainty),
                         ("indirect_2hop", 3, "needs_review"))
        evidence = page.sources[0]
        self.assertEqual(
            [(edge.caller_symbol_id, edge.callee_symbol_id) for edge in evidence.propagation_path],
            [("page.page", "dashboard.dashboard"),
             ("dashboard.dashboard", "report.report"),
             ("report.report", "utils.format_date")],
        )
        self.assertEqual(evidence.source_direct_impact, direct.findings[0])
        self.assertEqual((evidence.propagation_path[-1].file,
                          evidence.propagation_path[-1].line), (Path("report.py"), 3))

    def test_depth_limit_excludes_third_upstream_level(self):
        self.source("report.py", "from utils import format_date\ndef report():\n    format_date(1)\n")
        self.source("chain.py", "from report import report\ndef a():\n    report()\ndef b():\n    a()\ndef c():\n    b()\n")
        _, indirect = self.analyze()
        self.assertEqual({item.impacted_symbol_id for item in indirect.findings},
                         {"chain.a", "chain.b"})
        _, one_hop = self.analyze(max_depth=1)
        self.assertEqual({item.impacted_symbol_id for item in one_hop.findings}, {"chain.a"})
        _, zero_hop = self.analyze(max_depth=0)
        self.assertEqual(zero_hop.findings, ())

    def test_cycle_terminates_and_does_not_relabel_direct_caller(self):
        self.source("work.py", "from utils import format_date\ndef a():\n    format_date(1)\n    b()\ndef b():\n    a()\n")
        direct, indirect = self.analyze()
        self.assertEqual(direct.direct_impact_count, 1)
        self.assertEqual([(item.impacted_symbol_id, item.impact_type)
                          for item in indirect.findings], [("work.b", "indirect_1hop")])

    def test_multiple_paths_to_one_symbol_use_shortest_representative(self):
        self.source("work.py", "from utils import format_date\ndef report():\n"
                    "    format_date(1)\ndef dashboard():\n    report()\ndef page():\n"
                    "    report()\n    dashboard()\n")
        _, indirect = self.analyze()
        by_symbol = {item.impacted_symbol_id: item for item in indirect.findings}
        self.assertEqual(len(by_symbol), 2)
        page = by_symbol["work.page"]
        self.assertEqual(page.impact_type, "indirect_1hop")
        self.assertEqual(len(page.sources), 1)
        self.assertEqual(len(page.sources[0].propagation_path), 2)

    def test_multiple_direct_call_sites_keep_sources_without_duplicate_symbol(self):
        self.source("work.py", "from utils import format_date\ndef report_a():\n"
                    "    format_date(1)\ndef report_b():\n    format_date(2)\n"
                    "def page():\n    report_a()\n    report_b()\n")
        direct, indirect = self.analyze()
        self.assertEqual(direct.direct_impact_count, 2)
        self.assertEqual(len(indirect.findings), 1)
        page = indirect.findings[0]
        self.assertEqual((page.impacted_symbol_id, page.impact_type),
                         ("work.page", "indirect_1hop"))
        self.assertEqual(len(page.sources), 2)
        self.assertEqual({source.source_direct_impact.assessment.line for source in page.sources},
                         {3, 5})

    def test_preexisting_compatible_and_manual_calls_do_not_seed_propagation(self):
        self.source("work.py", "from utils import format_date\ndef old():\n"
                    "    format_date()\ndef improved():\n    format_date(1, 2)\n"
                    "def manual(args):\n    format_date(1, *args)\n"
                    "def upstream():\n    old()\n    improved()\n    manual(())\n")
        direct, indirect = self.analyze()
        self.assertEqual(direct.direct_impact_count, 0)
        self.assertEqual({item.effect for item in direct.assessments},
                         {"pre_existing_problem", "compatibility_improved", "manual_review"})
        self.assertEqual(indirect.findings, ())

    def test_manual_review_does_not_propagate_when_another_call_is_direct(self):
        self.source("work.py", "from utils import format_date\ndef definite():\n"
                    "    format_date(1)\ndef uncertain(args):\n"
                    "    format_date(1, *args)\ndef parent_definite():\n"
                    "    definite()\ndef parent_uncertain():\n    uncertain(())\n")
        direct, indirect = self.analyze()
        self.assertEqual(direct.direct_impact_count, 1)
        self.assertEqual({item.impacted_symbol_id for item in indirect.findings},
                         {"work.parent_definite"})

    def test_call_compatible_on_both_sides_has_no_upstream_impact(self):
        self.source("utils.py", "def format_date(date, **kwargs):\n    pass\n")
        self.source("work.py", "from utils import format_date\ndef report():\n"
                    "    format_date(1, timezone='UTC')\ndef page():\n    report()\n")
        graph = CallGraph(SymbolIndex(self.root).build()).build()
        before = FunctionSignature.from_definition(
            graph.index.symbols["utils.format_date"].definition
        )
        after = FunctionSignature("format_date", (
            Parameter("date", "positional_or_keyword"),
            Parameter("timezone", "keyword_only"),
            Parameter("kwargs", "var_keyword"),
        ))
        spec = ChangeSpec("add_required_parameter", "utils.format_date", before, after,
                          AddedParameter("timezone", "keyword_only"))
        direct = analyze_direct_impact(graph, spec)
        self.assertEqual(direct.assessments[0].effect, "no_impact")
        self.assertEqual(direct.direct_impact_count, 0)
        self.assertEqual(propagate_indirect_impact(graph, direct).findings, ())

    def test_unresolved_calls_cannot_form_upstream_path(self):
        self.source("report.py", "from utils import format_date\ndef report():\n"
                    "    format_date(1)\n")
        self.source("upper.py", "def caller(report):\n    report()\n")
        direct, indirect = self.analyze()
        self.assertEqual(direct.direct_impact_count, 1)
        self.assertEqual(indirect.findings, ())

    def test_invalid_depth_is_rejected(self):
        self.source("report.py", "from utils import format_date\ndef report():\n"
                    "    format_date(1)\n")
        graph = CallGraph(SymbolIndex(self.root).build()).build()
        before = FunctionSignature.from_definition(
            graph.index.symbols["utils.format_date"].definition
        )
        after = FunctionSignature("format_date", (*before.parameters,
                                                   Parameter("timezone", "positional_or_keyword")))
        spec = ChangeSpec("add_required_parameter", "utils.format_date", before, after,
                          AddedParameter("timezone", "positional_or_keyword"))
        direct = analyze_direct_impact(graph, spec)
        for depth in (-1, 3):
            with self.subTest(depth=depth), self.assertRaises(ValueError):
                propagate_indirect_impact(graph, direct, depth)


if __name__ == "__main__":
    unittest.main()
