"""Validate one structured required-parameter addition without editing source."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from openimpact.analysis.change_spec import (
    AddedParameter,
    ChangeSpec,
    FunctionSignature,
    validate_change_spec,
)
from openimpact.analysis.models import Parameter
from openimpact.analysis.symbol_index import SymbolIndex


class ChangeSpecTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name) / "project"
        self.root.mkdir()

    def source(self, relative_path: str, text: str) -> Path:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def index(self) -> SymbolIndex:
        return SymbolIndex(self.root).build()

    @staticmethod
    def spec(
        target: str = "utils.format_date",
        before: FunctionSignature | None = None,
        after: FunctionSignature | None = None,
        added: AddedParameter | None = None,
    ) -> ChangeSpec:
        return ChangeSpec(
            change_type="add_required_parameter",
            target_symbol_id=target,
            before=before or FunctionSignature("format_date", (Parameter("date", "positional_or_keyword"),)),
            after=after or FunctionSignature("format_date", (
                Parameter("date", "positional_or_keyword"),
                Parameter("timezone", "positional_or_keyword"),
            )),
            added_parameter=added or AddedParameter("timezone", "positional_or_keyword", True),
        )

    def test_valid_required_parameter_addition(self):
        self.source("utils.py", "def format_date(date):\n    return date\n")
        result = validate_change_spec(self.index(), self.spec())
        self.assertTrue(result.valid)
        self.assertEqual(result.diagnostics, ())
        self.assertEqual(result.current_signature, self.spec().before)

    def test_unknown_target_is_rejected(self):
        self.source("utils.py", "def format_date(date):\n    pass\n")
        result = validate_change_spec(self.index(), self.spec(target="missing.format_date"))
        self.assertFalse(result.valid)
        self.assertEqual(result.diagnostics[0].code, "target_not_found")

    def test_declared_before_signature_must_match_source(self):
        self.source("utils.py", "def format_date(date, timezone='UTC'):\n    pass\n")
        result = validate_change_spec(self.index(), self.spec())
        self.assertFalse(result.valid)
        self.assertEqual(result.diagnostics[0].code, "before_mismatch")

    def test_default_expression_difference_is_a_before_mismatch(self):
        self.source("utils.py", "def format_date(date, timezone='UTC'):\n    pass\n")
        before = FunctionSignature("format_date", (
            Parameter("date", "positional_or_keyword"),
            Parameter("timezone", "positional_or_keyword", True, "'LOCAL'"),
        ))
        result = validate_change_spec(self.index(), self.spec(before=before))
        self.assertEqual(result.diagnostics[0].code, "before_mismatch")

    def test_annotation_is_part_of_the_current_signature(self):
        self.source("utils.py", "def format_date(date: str) -> str:\n    return date\n")
        result = validate_change_spec(self.index(), self.spec())
        self.assertEqual(result.diagnostics[0].code, "before_mismatch")
        self.assertEqual(
            result.current_signature.parameters[0].annotation_source, "str"
        )
        self.assertEqual(result.current_signature.return_annotation_source, "str")

    def test_optional_added_parameter_is_rejected(self):
        self.source("utils.py", "def format_date(date):\n    pass\n")
        after = FunctionSignature("format_date", (
            Parameter("date", "positional_or_keyword"),
            Parameter("timezone", "positional_or_keyword", True, "'UTC'"),
        ))
        result = validate_change_spec(self.index(), self.spec(after=after))
        self.assertFalse(result.valid)
        self.assertEqual(result.diagnostics[0].code, "added_parameter_not_required")

    def test_deletion_and_renaming_are_not_accepted_as_addition(self):
        self.source("utils.py", "def format_date(date):\n    pass\n")
        for after in (
            FunctionSignature("format_date", ()),
            FunctionSignature("format_date", (Parameter("value", "positional_or_keyword"),)),
            FunctionSignature("renamed", (Parameter("date", "positional_or_keyword"),
                                          Parameter("timezone", "positional_or_keyword"))),
        ):
            with self.subTest(after=after):
                result = validate_change_spec(self.index(), self.spec(after=after))
                self.assertFalse(result.valid)

    def test_same_named_functions_are_matched_by_full_symbol_id(self):
        self.source("a.py", "def process(item):\n    pass\n")
        self.source("b.py", "def process(item, mode='safe'):\n    pass\n")
        before = FunctionSignature("process", (Parameter("item", "positional_or_keyword"),))
        after = FunctionSignature("process", (
            Parameter("item", "positional_or_keyword"),
            Parameter("flag", "positional_or_keyword"),
        ))
        spec_a = self.spec("a.process", before, after, AddedParameter("flag", "positional_or_keyword", True))
        spec_b = self.spec("b.process", before, after, AddedParameter("flag", "positional_or_keyword", True))
        index = self.index()
        self.assertTrue(validate_change_spec(index, spec_a).valid)
        self.assertEqual(validate_change_spec(index, spec_b).diagnostics[0].code, "before_mismatch")

    def test_required_positional_only_and_keyword_only_can_be_described(self):
        self.source("utils.py", "def format_date(date):\n    pass\n")
        keyword_after = FunctionSignature("format_date", (
            Parameter("date", "positional_or_keyword"), Parameter("timezone", "keyword_only"),
        ))
        keyword_spec = self.spec(after=keyword_after, added=AddedParameter("timezone", "keyword_only", True))
        self.assertTrue(validate_change_spec(self.index(), keyword_spec).valid)

        self.source("utils.py", "def format_date(date, /):\n    pass\n")
        positional_before = FunctionSignature("format_date", (Parameter("date", "positional_only"),))
        positional_after = FunctionSignature("format_date", (
            Parameter("date", "positional_only"), Parameter("timezone", "positional_only"),
        ))
        positional_spec = self.spec(
            before=positional_before, after=positional_after,
            added=AddedParameter("timezone", "positional_only", True),
        )
        self.assertTrue(validate_change_spec(self.index(), positional_spec).valid)

    def test_invalid_new_signature_order_is_rejected(self):
        self.source("utils.py", "def format_date(date='today'):\n    pass\n")
        before = FunctionSignature("format_date", (
            Parameter("date", "positional_or_keyword", True, "'today'"),
        ))
        after = FunctionSignature("format_date", (
            Parameter("date", "positional_or_keyword", True, "'today'"),
            Parameter("timezone", "positional_or_keyword"),
        ))
        result = validate_change_spec(self.index(), self.spec(before=before, after=after))
        self.assertEqual(result.diagnostics[0].code, "invalid_after_signature")

    def test_duplicate_new_parameter_name_is_rejected(self):
        self.source("utils.py", "def format_date(date):\n    pass\n")
        after = FunctionSignature("format_date", (
            Parameter("date", "positional_or_keyword"),
            Parameter("date", "positional_or_keyword"),
        ))
        self.assertEqual(
            validate_change_spec(self.index(), self.spec(after=after)).diagnostics[0].code,
            "invalid_after_signature",
        )

    def test_invalid_new_annotation_is_rejected_without_evaluating_it(self):
        self.source("utils.py", "def format_date(date):\n    pass\n")
        after = FunctionSignature("format_date", (
            Parameter("date", "positional_or_keyword"),
            Parameter("timezone", "positional_or_keyword", annotation_source="str["),
        ))
        spec = self.spec(
            after=after,
            added=AddedParameter("timezone", "positional_or_keyword", True, "str["),
        )
        self.assertEqual(
            validate_change_spec(self.index(), spec).diagnostics[0].code,
            "invalid_after_signature",
        )

    def test_non_module_level_method_cannot_be_targeted(self):
        self.source("utils.py", "class Formatter:\n    def format_date(self, date):\n        pass\n")
        result = validate_change_spec(self.index(), self.spec(target="utils.Formatter.format_date"))
        self.assertEqual(result.diagnostics[0].code, "target_not_found")

    def test_change_type_other_than_required_addition_is_rejected(self):
        self.source("utils.py", "def format_date(date):\n    pass\n")
        spec = self.spec()
        unsupported = ChangeSpec("unsupported_change", spec.target_symbol_id,
                                 spec.before, spec.after, spec.added_parameter)
        result = validate_change_spec(self.index(), unsupported)
        self.assertEqual(result.diagnostics[0].code, "unsupported_change_type")

    def test_validation_does_not_modify_source(self):
        path = self.source("utils.py", "# 中文注释\ndef format_date(date):\n    return date\n")
        original = path.read_bytes()
        validate_change_spec(self.index(), self.spec())
        self.assertEqual(path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
