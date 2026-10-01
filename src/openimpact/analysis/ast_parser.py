"""Read one Python file and extract syntax facts without executing it."""

import ast
import tokenize
from pathlib import Path

from openimpact.analysis.models import (
    FunctionCall,
    FunctionDefinition,
    ImportReference,
    Parameter,
    ParseDiagnostic,
    ParsedModule,
)


def _parameters(arguments: ast.arguments) -> tuple[Parameter, ...]:
    positional = [*arguments.posonlyargs, *arguments.args]
    first_default = len(positional) - len(arguments.defaults)
    result: list[Parameter] = []
    for index, argument in enumerate(arguments.posonlyargs):
        default = arguments.defaults[index - first_default] if index >= first_default else None
        result.append(Parameter(
            argument.arg, "positional_only", default is not None,
            ast.unparse(default) if default is not None else None,
            ast.unparse(argument.annotation) if argument.annotation is not None else None,
        ))
    for index, argument in enumerate(arguments.args, start=len(arguments.posonlyargs)):
        default = arguments.defaults[index - first_default] if index >= first_default else None
        result.append(Parameter(
            argument.arg, "positional_or_keyword", default is not None,
            ast.unparse(default) if default is not None else None,
            ast.unparse(argument.annotation) if argument.annotation is not None else None,
        ))
    if arguments.vararg is not None:
        argument = arguments.vararg
        result.append(Parameter(
            argument.arg, "var_positional", annotation_source=(
                ast.unparse(argument.annotation) if argument.annotation is not None else None
            ),
        ))
    for argument, default in zip(arguments.kwonlyargs, arguments.kw_defaults, strict=True):
        result.append(Parameter(
            argument.arg, "keyword_only", default is not None,
            ast.unparse(default) if default is not None else None,
            ast.unparse(argument.annotation) if argument.annotation is not None else None,
        ))
    if arguments.kwarg is not None:
        argument = arguments.kwarg
        result.append(Parameter(
            argument.arg, "var_keyword", annotation_source=(
                ast.unparse(argument.annotation) if argument.annotation is not None else None
            ),
        ))
    return tuple(result)


def _callee_syntax(expression: ast.expr) -> tuple[str, tuple[str, ...] | None]:
    if isinstance(expression, ast.Name):
        return "name", (expression.id,)
    if isinstance(expression, ast.Attribute):
        current: ast.expr = expression
        names: list[str] = []
        while isinstance(current, ast.Attribute):
            names.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            return "attribute", (current.id, *reversed(names))
    return "other", None


class _BoundNames(ast.NodeVisitor):
    """Conservatively collect names that can shadow a static function binding."""

    def __init__(self):
        self.names: set[str] = set()

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.names.add(node.id)

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.names.add(node.name)
        # A nested body has a different scope.

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.names.add(node.name)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        pass

    def visit_Import(self, node: ast.Import) -> None:
        self.names.update(alias.asname or alias.name.split(".")[0] for alias in node.names)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self.names.update(alias.asname or alias.name for alias in node.names)

    def visit_Global(self, node: ast.Global) -> None:
        self.names.update(node.names)

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        self.names.update(node.names)


def _bound_names(statements: list[ast.stmt]) -> frozenset[str]:
    collector = _BoundNames()
    for statement in statements:
        collector.visit(statement)
    return frozenset(collector.names)


class _CallCollector(ast.NodeVisitor):
    def __init__(self, path: Path):
        self.path = path
        self.calls: list[FunctionCall] = []
        self.enclosing_function: str | None = None

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        # Decorators and defaults execute when a definition is evaluated.
        for expression in (*node.decorator_list, *node.args.defaults):
            self.visit(expression)
        for expression in node.args.kw_defaults:
            if expression is not None:
                self.visit(expression)
        if self.enclosing_function is not None:
            return  # Nested function body is outside the supported scope.
        self.enclosing_function = node.name
        for statement in node.body:
            self.visit(statement)
        self.enclosing_function = None

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        # Class methods and class body calls are outside this release's scope.
        if self.enclosing_function is None:
            for expression in (*node.decorator_list, *node.bases):
                self.visit(expression)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        # A lambda body has its own scope; defaults evaluate in the parent scope.
        for expression in (*node.args.defaults, *node.args.kw_defaults):
            if expression is not None:
                self.visit(expression)

    def visit_Call(self, node: ast.Call) -> None:
        expression_type, callee_path = _callee_syntax(node.func)
        self.calls.append(
            FunctionCall(
                file=self.path,
                lineno=node.lineno,
                col_offset=node.col_offset,
                end_lineno=getattr(node, "end_lineno", None),
                expression_type=expression_type,
                expression=ast.unparse(node.func),
                callee_path=callee_path,
                enclosing_function=self.enclosing_function,
                positional_count=sum(not isinstance(arg, ast.Starred) for arg in node.args),
                keyword_names=frozenset(
                    keyword.arg for keyword in node.keywords if keyword.arg is not None
                ),
                has_star_args=any(isinstance(arg, ast.Starred) for arg in node.args),
                has_star_kwargs=any(keyword.arg is None for keyword in node.keywords),
            )
        )
        self.generic_visit(node)


def _failed(path: Path, diagnostic: ParseDiagnostic) -> ParsedModule:
    return ParsedModule(path, (), (), (), (diagnostic,))


class ASTParser:
    """Parse a source file into immutable, per-file syntax facts."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def parse(self) -> ParsedModule:
        # tokenize.open respects Python encoding declarations and UTF-8 BOMs.
        try:
            with tokenize.open(self.path) as source_file:
                source = source_file.read()
        except OSError as error:
            return _failed(self.path, ParseDiagnostic("read_error", str(error)))
        except (SyntaxError, UnicodeError, LookupError) as error:
            return _failed(
                self.path,
                ParseDiagnostic(
                    "encoding_error", str(error),
                    getattr(error, "lineno", None), getattr(error, "offset", None),
                ),
            )
        try:
            tree = ast.parse(source, filename=str(self.path))
        except SyntaxError as error:
            return _failed(
                self.path,
                ParseDiagnostic("syntax_error", error.msg, error.lineno, error.offset),
            )

        functions: list[FunctionDefinition] = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(
                    FunctionDefinition(
                        name=node.name,
                        lineno=node.lineno,
                        end_lineno=getattr(node, "end_lineno", None),
                        parameters=_parameters(node.args),
                        is_async=isinstance(node, ast.AsyncFunctionDef),
                        local_bindings=_bound_names(node.body),
                        return_annotation_source=(
                            ast.unparse(node.returns) if node.returns is not None else None
                        ),
                    )
                )

        # First release records direct module-level imports only. Nested imports
        # need scope metadata before a symbol index can use them safely.
        imports: list[ImportReference] = []
        for node in tree.body:
            if isinstance(node, ast.Import):
                for name in node.names:
                    imports.append(
                        ImportReference(
                            "import", name.name, None, name.asname, 0,
                            node.lineno, getattr(node, "end_lineno", None),
                        )
                    )
            elif isinstance(node, ast.ImportFrom):
                for name in node.names:
                    imports.append(
                        ImportReference(
                            "from_import", node.module, name.name, name.asname,
                            node.level, node.lineno, getattr(node, "end_lineno", None),
                        )
                    )

        collector = _CallCollector(self.path)
        collector.visit(tree)
        module_rebindings = _bound_names(
            [
                statement for statement in tree.body
                if not isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef,
                                              ast.Import, ast.ImportFrom))
            ]
        )
        return ParsedModule(
            path=self.path,
            functions=tuple(functions),
            imports=tuple(sorted(imports, key=lambda item: item.lineno)),
            calls=tuple(sorted(collector.calls, key=lambda item: (item.lineno, item.col_offset))),
            module_rebindings=module_rebindings,
        )
