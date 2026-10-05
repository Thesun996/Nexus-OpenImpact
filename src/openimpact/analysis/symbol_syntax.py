"""Variable definitions and reads from the existing AST; no target code runs."""

import ast
from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class VariableSyntax:
    name: str
    line: int
    column: int
    end_line: int
    end_column: int
    expression: str
    value_source: str | None
    annotation_source: str | None
    reason: str | None


@dataclass(frozen=True)
class ReadSyntax:
    kind: str
    path: tuple[str, ...]
    line: int
    column: int
    end_line: int
    end_column: int
    expression: str
    scope: str
    shadowed: bool


class Bindings(ast.NodeVisitor):
    def __init__(self):
        self.names = []
        self.globals = set()

    def visit_Name(self, node):
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.names.append(node.id)

    def visit_Import(self, node):
        self.names.extend(a.asname or a.name.split('.')[0] for a in node.names)

    def visit_ImportFrom(self, node):
        self.names.extend(a.asname or a.name for a in node.names)

    def visit_FunctionDef(self, node):
        self.names.append(node.name)
        # Defaults, decorators and annotations belong to the enclosing scope;
        # a NamedExpr there must participate in rebinding/conflict checks.
        for expression in [*node.decorator_list, *node.args.defaults,
                           *(item for item in node.args.kw_defaults if item is not None)]:
            self.visit(expression)
        for argument in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs,
                         *([node.args.vararg] if node.args.vararg else []),
                         *([node.args.kwarg] if node.args.kwarg else [])]:
            if argument.annotation is not None: self.visit(argument.annotation)
        if node.returns is not None: self.visit(node.returns)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        self.names.append(node.name)
        for expression in [*node.decorator_list, *node.bases, *(item.value for item in node.keywords)]:
            self.visit(expression)

    def visit_Global(self, node):
        self.globals.update(node.names)

    def visit_ExceptHandler(self, node):
        if node.name: self.names.append(node.name)
        self.generic_visit(node)

    def visit_MatchAs(self, node):
        if node.name: self.names.append(node.name)
        self.generic_visit(node)

    def visit_MatchStar(self, node):
        if node.name: self.names.append(node.name)

    def visit_MatchMapping(self, node):
        if node.rest: self.names.append(node.rest)
        self.generic_visit(node)

    def visit_Lambda(self, node):
        pass

    def visit_ListComp(self, node):
        # NamedExpr can leak into an enclosing scope. Flag it, not loop locals.
        for child in ast.walk(node):
            if isinstance(child, ast.NamedExpr):
                self.visit(child.target)

    visit_SetComp = visit_ListComp
    visit_DictComp = visit_ListComp
    visit_GeneratorExp = visit_ListComp


def bindings(body):
    visitor = Bindings()
    for node in body:
        visitor.visit(node)
    return visitor


def literal(node):
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        return isinstance(node.operand, ast.Constant) and isinstance(node.operand.value, (int, float, complex))
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return all(literal(item) for item in node.elts)
    if isinstance(node, ast.Dict):
        return all(key is not None and literal(key) and literal(value) for key, value in zip(node.keys, node.values))
    return False


def collect_symbol_facts(tree, source):
    top = {id(node) for node in tree.body}
    module_binds = bindings(tree.body)
    counts = Counter(module_binds.names)
    # Any statically declared global write defeats the unique-definition contract.
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound = bindings(node.body)
            for name in bound.names:
                if name in bound.globals:
                    counts[name] += 1
    definitions = []
    candidates = ModuleAssignments()
    candidates.visit(tree)
    for node in candidates.nodes:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        if isinstance(node, ast.Assign):
            targets, value, annotation = node.targets, node.value, None
        else:
            targets, value, annotation = [node.target], node.value, ast.unparse(node.annotation)
        # Only module scope assignments are candidates; functions are skipped
        # below through parent classification, not accidentally registered.
        names = [target.id for target in targets if isinstance(target, ast.Name)]
        if not names:
            names = [child.id for target in targets for child in ast.walk(target) if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store)]
        for name in names:
            reason = None
            if name.startswith('_'):
                reason = 'private_symbol_unsupported'
            elif id(node) not in top:
                reason = 'conditional_definition_unsupported'
            elif len(targets) != 1 or not isinstance(targets[0], ast.Name) or value is None or not literal(value):
                reason = 'complex_definition_unsupported'
            elif counts[name] != 1:
                reason = 'symbol_rebound'
            elif '__getattr__' in module_binds.names or '__dir__' in module_binds.names:
                reason = 'dynamic_exports_unsupported'
            definitions.append(VariableSyntax(name, node.lineno, node.col_offset, node.end_lineno, node.end_col_offset,
                                              ast.get_source_segment(source, node) or ast.unparse(node),
                                              ast.unparse(value) if value is not None else None, annotation, reason))
    collector = ReadCollector(source, tree)
    collector.visit(tree)
    if any(code == 'dynamic_definition_unsupported' for code, _, _ in collector.diagnostics):
        from dataclasses import replace
        definitions = [replace(item, reason=item.reason or 'dynamic_definition_unsupported') for item in definitions]
    return tuple(definitions), tuple(collector.reads), frozenset(module_binds.names), tuple(collector.diagnostics), tuple(sorted(counts.items()))


class ModuleAssignments(ast.NodeVisitor):
    def __init__(self): self.nodes = []
    def visit_Assign(self, node): self.nodes.append(node)
    def visit_AnnAssign(self, node): self.nodes.append(node)
    def visit_FunctionDef(self, node): pass
    visit_AsyncFunctionDef = visit_FunctionDef
    visit_ClassDef = visit_FunctionDef


class ReadCollector(ast.NodeVisitor):
    def __init__(self, source, tree):
        self.source = source
        self.scope = 'module'
        self.locals = set()
        self.reads = []
        self.diagnostics = []
        reflective = {'getattr', 'setattr', 'delattr', 'globals', 'locals', 'vars', 'exec', 'eval', '__import__'}
        self.reflective_names = {name: name for name in reflective}
        self.builtin_modules = {'builtins'}
        # These aliases only trigger conservative diagnostics. They do not
        # resolve an arbitrary callable or establish a definite project edge.
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                self.builtin_modules.update(alias.asname or alias.name for alias in node.names if alias.name == 'builtins')
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module == 'builtins':
                self.reflective_names.update({alias.asname or alias.name: alias.name for alias in node.names if alias.name in reflective})

    def record(self, node, kind, path):
        self.reads.append(ReadSyntax(kind, path, node.lineno, node.col_offset, node.end_lineno, node.end_col_offset,
                                     ast.get_source_segment(self.source, node) or ast.unparse(node), self.scope, path[0] in self.locals))

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Load):
            self.record(node, 'name_read', (node.id,))

    def visit_Attribute(self, node):
        if node.attr == '__dict__' or self.scope == 'unsupported_scope' and not isinstance(node.ctx, ast.Load):
            # An escaping namespace or an unsupported-scope attribute store
            # can recreate a removed name. Without data flow, require review.
            self.diagnostics.append(('dynamic_symbol_write', node.lineno, node.col_offset))
        if isinstance(node.value, ast.Name):
            self.record(node, 'attribute_read' if isinstance(node.ctx, ast.Load) else 'attribute_write', (node.value.id, node.attr))
        else:
            # A nested attribute cannot be interpreted as an arbitrary object.
            self.diagnostics.append(('complex_attribute_unsupported', node.lineno, node.col_offset))
            self.visit(node.value)

    def visit_Call(self, node):
        name = self.reflective_names.get(node.func.id) if isinstance(node.func, ast.Name) else None
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id in self.builtin_modules:
            name = self.reflective_names.get(node.func.attr)
        if name:
            code = 'dynamic_definition_unsupported' if name in {'exec', 'eval', 'globals'} or self.scope == 'module' and name == 'locals' else 'dynamic_symbol_reference'
            self.diagnostics.append((code, node.lineno, node.col_offset))
            if name in {'setattr', 'delattr', 'vars', 'exec', 'eval'}:
                # Without data flow these APIs may mutate another module's
                # namespace. Preserve this boundary across source files.
                self.diagnostics.append(('dynamic_symbol_write', node.lineno, node.col_offset))
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        for expr in [*node.decorator_list, *node.args.defaults, *(x for x in node.args.kw_defaults if x is not None)]:
            self.visit(expr)
        old = self.scope, self.locals
        bound = bindings(node.body)
        args = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
        if node.args.vararg: args.append(node.args.vararg)
        if node.args.kwarg: args.append(node.args.kwarg)
        for annotation in [*(arg.annotation for arg in args if arg.annotation), *([node.returns] if node.returns else [])]:
            self.unsupported(annotation)
        self.scope = 'function' if old[0] == 'module' else 'unsupported_scope'
        self.locals = (set(bound.names) | {arg.arg for arg in args}) - bound.globals
        if old[0] != 'module': self.locals |= old[1]
        for child in node.body: self.visit(child)
        self.scope, self.locals = old

    visit_AsyncFunctionDef = visit_FunctionDef

    def unsupported(self, node):
        old = self.scope, self.locals
        self.scope = 'unsupported_scope'
        if isinstance(node, (ast.Name, ast.Attribute)):
            self.visit(node)
        else:
            self.generic_visit(node)
        self.scope, self.locals = old

    visit_ClassDef = unsupported
    visit_Lambda = unsupported
    visit_ListComp = unsupported
    visit_SetComp = unsupported
    visit_DictComp = unsupported
    visit_GeneratorExp = unsupported

    def visit_AnnAssign(self, node):
        self.visit(node.target)
        if node.value is not None: self.visit(node.value)
        self.unsupported(node.annotation)
