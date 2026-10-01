"""Direct compatibility is assessed only for resolved calls to one symbol."""

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
from openimpact.analysis.models import Parameter
from openimpact.analysis.symbol_index import SymbolIndex


class DirectImpactTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name) / "project"
        self.root.mkdir()

    def source(self, name: str, body: str) -> None:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")

    def analyze(
        self, added_kind: str = "positional_or_keyword", target: str = "utils.f"
    ):
        graph = CallGraph(SymbolIndex(self.root).build()).build()
        before = FunctionSignature.from_definition(graph.index.symbols[target].definition)
        after = FunctionSignature(
            before.name,
            (*before.parameters, Parameter("extra", added_kind)),
            before.is_async,
            before.return_annotation_source,
        )
        spec = ChangeSpec(
            "add_required_parameter", target, before, after,
            AddedParameter("extra", added_kind, True),
        )
        return analyze_direct_impact(graph, spec)

    def test_missing_required_parameter_is_incompatible_with_location(self):
        self.source("utils.py", "def f(a):\n    pass\n")
        self.source("report.py", "from utils import f\ndef report(x):\n    f(x)\n")
        result = self.analyze()
        self.assertTrue(result.validation.valid)
        self.assertEqual(len(result.findings), 1)
        finding = result.findings[0]
        self.assertEqual(finding.effect, "direct_impact")
        self.assertEqual(result.direct_impact_count, 1)
        assessment = finding.assessment
        self.assertEqual((assessment.before_status, assessment.after_status),
                         ("compatible", "incompatible"))
        self.assertEqual(assessment.after_rule_id, "required_parameter_missing")
        self.assertIn("extra", finding.reason)
        self.assertEqual(
            (assessment.file, assessment.line, assessment.col_offset), (Path("report.py"), 3, 4)
        )
        self.assertEqual(
            (assessment.caller_symbol_id, assessment.target_symbol_id, finding.impact_type),
            ("report.report", "utils.f", "direct"),
        )
        self.assertEqual(assessment.change_spec.target_symbol_id, "utils.f")

    def test_second_positional_argument_is_compatible(self):
        self.source("utils.py", "def f(a):\n    pass\n")
        self.source("report.py", "from utils import f\ndef report():\n    f(1, 2)\n")
        result = self.analyze()
        self.assertEqual(result.assessments[0].effect, "compatibility_improved")
        self.assertEqual(result.findings, ())
        self.assertEqual(result.direct_impact_count, 0)

    def test_call_already_missing_old_argument_is_pre_existing_problem(self):
        self.source("utils.py", "def f(a):\n    pass\n")
        self.source("report.py", "from utils import f\ndef report():\n    f()\n")
        result = self.analyze()
        assessment = result.assessments[0]
        self.assertEqual((assessment.before_status, assessment.after_status),
                         ("incompatible", "incompatible"))
        self.assertEqual(assessment.effect, "pre_existing_problem")
        self.assertEqual(result.findings, ())
        self.assertEqual(result.direct_impact_count, 0)

    def test_call_compatible_before_and_after_is_no_impact(self):
        self.source("utils.py", "def f(a, **kwargs):\n    pass\n")
        self.source("report.py", "from utils import f\ndef report():\n    f(1, extra=2)\n")
        graph = CallGraph(SymbolIndex(self.root).build()).build()
        before = FunctionSignature.from_definition(graph.index.symbols["utils.f"].definition)
        after = FunctionSignature("f", (
            Parameter("a", "positional_or_keyword"),
            Parameter("extra", "keyword_only"),
            Parameter("kwargs", "var_keyword"),
        ))
        spec = ChangeSpec("add_required_parameter", "utils.f", before, after,
                          AddedParameter("extra", "keyword_only"))
        result = analyze_direct_impact(graph, spec)
        self.assertTrue(result.validation.valid)
        self.assertEqual((result.assessments[0].before_status,
                          result.assessments[0].after_status),
                         ("compatible", "compatible"))
        self.assertEqual(result.assessments[0].effect, "no_impact")
        self.assertEqual(result.findings, ())
        self.assertEqual(result.direct_impact_count, 0)

    def test_keyword_argument_is_compatible(self):
        self.source("utils.py", "def f(a):\n    pass\n")
        self.source("report.py", "from utils import f\ndef report():\n    f(1, extra=2)\n")
        result = self.analyze()
        self.assertEqual((result.assessments[0].before_status,
                          result.assessments[0].after_status),
                         ("incompatible", "compatible"))
        self.assertEqual(result.findings, ())

    def test_module_attribute_and_alias_use_resolved_target(self):
        self.source("utils.py", "def f(a):\n    pass\n")
        self.source(
            "report.py", "import utils\nimport utils as u\ndef report():\n"
            "    utils.f(1)\n    u.f(1, 2)\n",
        )
        result = self.analyze()
        self.assertEqual([item.effect for item in result.assessments],
                         ["direct_impact", "compatibility_improved"])
        self.assertEqual({item.resolution_basis for item in result.assessments},
                         {"module_import"})
        self.assertEqual(result.direct_impact_count, 1)

    def test_keyword_only_added_parameter(self):
        self.source("utils.py", "def f(a):\n    pass\n")
        self.source(
            "report.py", "from utils import f\ndef report():\n    f(1)\n    f(1, extra=2)\n"
        )
        result = self.analyze("keyword_only")
        self.assertEqual([item.effect for item in result.assessments],
                         ["direct_impact", "compatibility_improved"])
        self.assertEqual(result.direct_impact_count, 1)

    def test_positional_only_added_parameter(self):
        self.source("utils.py", "def f(a, /):\n    pass\n")
        self.source(
            "report.py",
            "from utils import f\ndef report():\n    f(1)\n    f(1, 2)\n    f(1, extra=2)\n",
        )
        result = self.analyze("positional_only")
        assessments = result.assessments
        self.assertEqual(
            [item.effect for item in assessments],
            ["direct_impact", "compatibility_improved", "pre_existing_problem"],
        )
        self.assertEqual(assessments[2].after_rule_id, "unexpected_keyword_argument")
        self.assertEqual(result.direct_impact_count, 1)

    def test_star_args_require_manual_review(self):
        self.source("utils.py", "def f(a):\n    pass\n")
        self.source("report.py", "from utils import f\ndef report(args):\n    f(1, *args)\n")
        result = self.analyze()
        self.assertEqual(result.assessments[0].effect, "manual_review")
        self.assertEqual(result.findings[0].effect, "manual_review")
        self.assertEqual(result.direct_impact_count, 0)

    def test_star_kwargs_require_manual_review(self):
        self.source("utils.py", "def f(a):\n    pass\n")
        self.source("report.py", "from utils import f\ndef report(kwargs):\n    f(1, **kwargs)\n")
        result = self.analyze()
        self.assertEqual((result.assessments[0].before_status,
                          result.assessments[0].after_status),
                         ("manual_review", "manual_review"))
        self.assertEqual(result.direct_impact_count, 0)

    def test_target_symbol_id_prevents_same_name_cross_talk(self):
        self.source("utils.py", "def f(a):\n    pass\n")
        self.source("other.py", "def f(a):\n    pass\n")
        self.source(
            "report.py", "from utils import f as wanted\nfrom other import f as unrelated\n"
            "def report():\n    wanted(1)\n    unrelated(1)\n",
        )
        assessments = self.analyze().assessments
        self.assertEqual(len(assessments), 1)
        self.assertEqual((assessments[0].line, assessments[0].target_symbol_id),
                         (4, "utils.f"))

    def test_unresolved_and_module_level_calls_do_not_become_direct_findings(self):
        self.source("utils.py", "def f(a):\n    pass\n")
        self.source(
            "report.py", "from utils import f\nfrom missing import f as unknown\n"
            "f(1)\ndef report():\n    unknown(1)\n    f(1)\n",
        )
        assessments = self.analyze().assessments
        self.assertEqual(len(assessments), 1)
        self.assertEqual(assessments[0].line, 6)

    def test_multiple_calls_are_assessed_individually_even_on_same_line(self):
        self.source("utils.py", "def f(a):\n    pass\n")
        self.source("report.py", "from utils import f\ndef report():\n    f(1); f(1, 2)\n")
        result = self.analyze()
        assessments = result.assessments
        self.assertEqual(len(assessments), 2)
        self.assertEqual([item.effect for item in assessments],
                         ["direct_impact", "compatibility_improved"])
        self.assertEqual({item.line for item in assessments}, {3})
        self.assertEqual(len({item.col_offset for item in assessments}), 2)
        self.assertEqual(result.direct_impact_count, 1)

    def test_old_optional_parameter_does_not_hide_new_required_parameter(self):
        self.source("utils.py", "def f(a=1, *, mode='x'):\n    pass\n")
        self.source("report.py", "from utils import f\ndef report():\n    f()\n")
        self.assertEqual(self.analyze("keyword_only").assessments[0].after_rule_id,
                         "required_parameter_missing")

    def test_existing_varargs_accept_extra_fixed_positionals(self):
        self.source("utils.py", "def f(a, *args):\n    pass\n")
        self.source("report.py", "from utils import f\ndef report():\n    f(1, 2)\n")
        # A new keyword-only parameter is still missing despite *args in the definition.
        result = self.analyze("keyword_only")
        self.assertEqual(result.assessments[0].effect, "direct_impact")

    def test_excess_positionals_and_duplicate_keyword_are_incompatible(self):
        self.source("utils.py", "def f(a):\n    pass\n")
        self.source(
            "report.py", "from utils import f\ndef report():\n"
            "    f(1, 2, 3)\n    f(1, a=2, extra=3)\n",
        )
        assessments = self.analyze().assessments
        self.assertEqual(
            [item.after_rule_id for item in assessments],
            ["too_many_positional_arguments", "multiple_values_for_parameter"],
        )
        self.assertTrue(all(item.effect == "pre_existing_problem" for item in assessments))

    def test_invalid_change_spec_produces_no_assessments(self):
        self.source("utils.py", "def f(a):\n    pass\n")
        self.source("report.py", "from utils import f\ndef report():\n    f(1)\n")
        graph = CallGraph(SymbolIndex(self.root).build()).build()
        before = FunctionSignature("f", ())
        spec = ChangeSpec(
            "add_required_parameter", "utils.f", before,
            FunctionSignature("f", (Parameter("extra", "positional_or_keyword"),)),
            AddedParameter("extra", "positional_or_keyword"),
        )
        result = analyze_direct_impact(graph, spec)
        self.assertFalse(result.validation.valid)
        self.assertEqual(result.validation.diagnostics[0].code, "before_mismatch")
        self.assertEqual(result.assessments, ())
        self.assertEqual(result.findings, ())


if __name__ == "__main__":
    unittest.main()
