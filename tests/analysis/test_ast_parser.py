"""Tests for per-file Python syntax facts."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from openimpact.analysis.ast_parser import ASTParser
from openimpact.analysis.models import Parameter, ParsedModule


class ASTParserTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "sample.py"

    def parse(self, source: str):
        self.path.write_text(source, encoding="utf-8")
        return ASTParser(self.path).parse()

    def test_module_functions_and_parameter_kinds(self):
        result = self.parse(
            "def format_date(date, /, locale='zh', *args, timezone, mode='short', **kw):\n"
            "    return date\n"
            "\n"
            "async def report(value):\n"
            "    return value\n"
            "class Formatter:\n"
            "    def method(self):\n"
            "        pass\n"
        )
        self.assertEqual([item.name for item in result.functions], ["format_date", "report"])
        self.assertEqual((result.functions[0].lineno, result.functions[0].end_lineno), (1, 2))
        self.assertFalse(result.functions[0].is_async)
        self.assertTrue(result.functions[1].is_async)
        self.assertEqual(
            result.functions[0].parameters,
            (
                Parameter("date", "positional_only"),
                Parameter("locale", "positional_or_keyword", True, "'zh'"),
                Parameter("args", "var_positional"),
                Parameter("timezone", "keyword_only"),
                Parameter("mode", "keyword_only", True, "'short'"),
                Parameter("kw", "var_keyword"),
            ),
        )
        self.assertEqual(result.diagnostics, ())

    def test_positional_defaults_cross_slash_boundary(self):
        result = self.parse("def f(a, b=1, /, c=2):\n    pass\n")
        self.assertEqual(
            result.functions[0].parameters,
            (
                Parameter("a", "positional_only"),
                Parameter("b", "positional_only", True, "1"),
                Parameter("c", "positional_or_keyword", True, "2"),
            ),
        )

    def test_required_positional_only_and_optional_positional_or_keyword(self):
        result = self.parse("def f(a, /, b=1):\n    pass\n")
        self.assertEqual(
            result.functions[0].parameters,
            (
                Parameter("a", "positional_only", False),
                Parameter("b", "positional_or_keyword", True, "1"),
            ),
        )

    def test_import_forms_preserve_module_name_alias_and_relative_level(self):
        result = self.parse(
            "import utils\n"
            "import utils as u\n"
            "from utils import format_date\n"
            "from utils import format_date as fd\n"
            "from .helpers import helper as h\n"
        )
        self.assertEqual(
            [(item.import_type, item.module, item.imported_name, item.alias, item.level, item.lineno)
             for item in result.imports],
            [
                ("import", "utils", None, None, 0, 1),
                ("import", "utils", None, "u", 0, 2),
                ("from_import", "utils", "format_date", None, 0, 3),
                ("from_import", "utils", "format_date", "fd", 0, 4),
                ("from_import", "helpers", "helper", "h", 1, 5),
            ],
        )

    def test_nested_imports_do_not_appear_as_module_imports(self):
        result = self.parse(
            "import top_level\n"
            "def f():\n"
            "    import local_only\n"
            "class C:\n"
            "    from inside_class import method\n"
        )
        self.assertEqual([item.module for item in result.imports], ["top_level"])

    def test_calls_are_locations_only_and_methods_are_out_of_scope(self):
        result = self.parse(
            "started()\n"
            "from utils import format_date\n"
            "def report(x):\n"
            "    return format_date(x)\n"
            "def wrapper(x):\n"
            "    def nested():\n"
            "        return hidden()\n"
            "    return report(x)\n"
            "class C:\n"
            "    def method(self):\n"
            "        return hidden_method()\n"
        )
        self.assertEqual(
            [(item.expression, item.lineno, item.enclosing_function) for item in result.calls],
            [("started", 1, None), ("format_date", 4, "report"), ("report", 8, "wrapper")],
        )

    def test_unsupported_scopes_do_not_enter_supported_calls(self):
        result = self.parse(
            "def outer():\n"
            "    def inner():\n"
            "        return nested_call()\n"
            "    return direct_call()\n"
            "class Example:\n"
            "    def method(self):\n"
            "        return method_call()\n"
        )
        self.assertEqual(
            [(call.expression, call.enclosing_function) for call in result.calls],
            [("direct_call", "outer")],
        )

    def test_direct_attribute_and_aliased_calls_keep_argument_shapes(self):
        result = self.parse(
            "import utils\n"
            "from utils import format_date as fd\n"
            "def report(x):\n"
            "    a = format_date(x)\n"
            "    b = utils.format_date(x)\n"
            "    return fd(x, timezone='UTC')\n"
        )
        self.assertEqual(
            [(item.expression_type, item.expression, item.callee_path, item.lineno,
              item.positional_count, item.keyword_names, item.file, item.enclosing_function)
             for item in result.calls],
            [
                ("name", "format_date", ("format_date",), 4, 1, frozenset(), self.path,
                 "report"),
                ("attribute", "utils.format_date", ("utils", "format_date"), 5, 1,
                 frozenset(), self.path, "report"),
                ("name", "fd", ("fd",), 6, 1, frozenset({"timezone"}), self.path,
                 "report"),
            ],
        )

    def test_long_attribute_chain_and_dynamic_callee(self):
        result = self.parse("package.utils.format_date(x)\nfactory()(x)\n")
        self.assertEqual(
            [(call.expression_type, call.callee_path) for call in result.calls],
            [
                ("attribute", ("package", "utils", "format_date")),
                ("other", None),
                ("name", ("factory",)),
            ],
        )

    def test_starred_arguments_are_marked_unknown(self):
        result = self.parse("def f(values, options):\n    return target(*values, **options)\n")
        self.assertEqual(result.calls[0].positional_count, 0)
        self.assertEqual(result.calls[0].keyword_names, frozenset())
        self.assertTrue(result.calls[0].has_star_args)
        self.assertTrue(result.calls[0].has_star_kwargs)

    def test_known_arguments_are_counted_with_starred_expansions(self):
        result = self.parse("f(1, *args, mode='x', **kwargs)\n")
        call = result.calls[0]
        self.assertEqual(call.positional_count, 1)
        self.assertEqual(call.keyword_names, frozenset({"mode"}))
        self.assertTrue(call.has_star_args)
        self.assertTrue(call.has_star_kwargs)

    def test_syntax_error_is_reported_without_partial_facts(self):
        result = self.parse("def broken(:\n    pass\n")
        self.assertEqual((result.functions, result.imports, result.calls), ((), (), ()))
        self.assertEqual(len(result.diagnostics), 1)
        self.assertEqual(result.diagnostics[0].kind, "syntax_error")
        self.assertEqual(result.diagnostics[0].lineno, 1)

    def test_python_encoding_cookie_is_respected(self):
        self.path.write_bytes(b"# coding: latin-1\nname = '\xe9'\n")
        result = ASTParser(self.path).parse()
        self.assertEqual(result.diagnostics, ())
        self.assertEqual(result.path, self.path)

    def test_invalid_source_encoding_is_a_diagnostic(self):
        self.path.write_bytes(b"# coding: utf-8\nname = '\xff'\n")
        result = ASTParser(self.path).parse()
        self.assertEqual((result.functions, result.imports, result.calls), ((), (), ()))
        self.assertEqual(len(result.diagnostics), 1)
        self.assertEqual(result.diagnostics[0].kind, "encoding_error")

    def test_missing_file_is_read_error_without_facts(self):
        result = ASTParser(self.path).parse()
        self.assertIsInstance(result, ParsedModule)
        self.assertEqual((result.functions, result.imports, result.calls), ((), (), ()))
        self.assertEqual(result.diagnostics[0].kind, "read_error")

    def test_source_is_parsed_without_execution(self):
        result = self.parse("raise RuntimeError('do not execute')\n")
        self.assertEqual(result.diagnostics, ())
        self.assertEqual(result.functions, ())


if __name__ == "__main__":
    unittest.main()
