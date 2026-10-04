"""Additional import facts from the already-parsed AST; no name binding here."""

import ast

from openimpact.analysis.models import ModuleImportSyntax, ModuleSyntaxDiagnostic


def collect_module_imports(tree: ast.Module, source: str):
    top_level = {id(node) for node in tree.body}
    nodes = sorted((node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))),
                   key=lambda node: (node.lineno, node.col_offset))
    references = []
    importlib_names = {"importlib"}
    dynamic_names = {"__import__"}
    for ordinal, node in enumerate(nodes):
        for member_index, member in enumerate(node.names):
            references.append(ModuleImportSyntax(
                "import" if isinstance(node, ast.Import) else "from_import",
                member.name if isinstance(node, ast.Import) else node.module,
                None if isinstance(node, ast.Import) else member.name,
                member.asname, 0 if isinstance(node, ast.Import) else node.level,
                node.lineno, node.col_offset, node.end_lineno, node.end_col_offset,
                ordinal, member_index, "top_level" if id(node) in top_level else "unsupported_scope",
                ast.get_source_segment(source, node) or ast.unparse(node),
            ))
            if isinstance(node, ast.Import) and member.name == "importlib":
                importlib_names.add(member.asname or "importlib")
            if isinstance(node, ast.ImportFrom) and node.module == "importlib" and member.name == "import_module":
                dynamic_names.add(member.asname or member.name)
    diagnostics = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callee = node.func
        dynamic = (isinstance(callee, ast.Name) and callee.id in dynamic_names
                   or isinstance(callee, ast.Attribute) and callee.attr == "import_module"
                   and isinstance(callee.value, ast.Name) and callee.value.id in importlib_names)
        reflective = isinstance(callee, ast.Name) and callee.id in {"exec", "eval"}
        if dynamic or reflective:
            diagnostics.append(ModuleSyntaxDiagnostic(
                "dynamic_import_unsupported" if dynamic else "dynamic_execution_unsupported",
                "动态导入/执行不在当前静态模块解析范围，需人工检查。", node.lineno, node.col_offset,
            ))
    return tuple(references), tuple(sorted(diagnostics, key=lambda item: (item.line, item.column)))
