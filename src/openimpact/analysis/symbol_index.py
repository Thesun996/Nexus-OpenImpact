"""Index project modules and functions, then bind explicit local imports."""

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from openimpact.analysis.ast_parser import ASTParser
from openimpact.analysis.models import (
    CallScope,
    FunctionDefinition,
    ImportReference,
    ParseDiagnostic,
    ParsedModule,
)
from openimpact.repository.scanner import RepositoryScanner
from openimpact.repository.layout import module_name, validate_analysis_root


@dataclass(frozen=True)
class Symbol:
    symbol_id: str
    module: str
    qualified_name: str
    file: Path
    definition: FunctionDefinition | CallScope


@dataclass(frozen=True)
class ImportBinding:
    source_module: str
    local_name: str
    source_file: Path
    lineno: int
    status: Literal["resolved", "unresolved"]
    kind: Literal["module", "function"] | None = None
    target_module: str | None = None
    target_symbol_id: str | None = None
    reason: str | None = None


def _module_name(relative_path: Path) -> str:
    return module_name(relative_path)


class SymbolIndex:
    """Project-level identity map; it never inspects or resolves calls."""

    def __init__(self, project_path: str | Path, *, analysis_root: str = "."):
        self.scanner = RepositoryScanner(project_path)
        self.analysis_root = validate_analysis_root(self.scanner.project_path, analysis_root)
        self.modules: dict[str, Path] = {}
        self.symbols: dict[str, Symbol] = {}
        self.callers: dict[str, Symbol] = {}
        self.bindings: dict[str, dict[str, ImportBinding]] = {}
        self.parsed_modules: dict[str, ParsedModule] = {}
        self.parsed_files: dict[Path, ParsedModule] = {}
        self.parse_diagnostics: dict[Path, tuple[ParseDiagnostic, ...]] = {}
        self.ambiguous_modules: set[str] = set()
        self.ambiguous_symbols: set[str] = set()

    def build(self) -> "SymbolIndex":
        self.modules.clear()
        self.symbols.clear()
        self.callers.clear()
        self.bindings.clear()
        self.parsed_modules.clear()
        self.parsed_files.clear()
        self.parse_diagnostics.clear()
        self.ambiguous_modules.clear()
        self.ambiguous_symbols.clear()

        paths_by_module: dict[str, list[Path]] = defaultdict(list)
        parsed_by_path: dict[Path, ParsedModule] = {}
        for relative_path in self.scanner.scan():
            module = self.module_name(relative_path)
            paths_by_module[module].append(relative_path)
            parsed = ASTParser(self.scanner.project_path / relative_path).parse()
            parsed_by_path[relative_path] = parsed
            self.parsed_files[relative_path] = parsed
            if parsed.diagnostics:
                self.parse_diagnostics[relative_path] = parsed.diagnostics

        for module, paths in paths_by_module.items():
            if len(paths) == 1:
                self.modules[module] = paths[0]
            else:
                self.ambiguous_modules.add(module)

        for module, relative_path in self.modules.items():
            parsed = parsed_by_path[relative_path]
            self.parsed_modules[module] = parsed
            if parsed.diagnostics:
                continue
            counts = Counter(function.name for function in parsed.functions)
            for function in parsed.functions:
                symbol_id = f"{module}.{function.name}"
                if counts[function.name] > 1:
                    self.ambiguous_symbols.add(symbol_id)
                    continue
                self.symbols[symbol_id] = Symbol(
                    symbol_id, module, function.name, relative_path, function
                )

            callers = (*(parsed.caller_definitions or parsed.functions), *parsed.call_scopes)
            caller_counts = Counter(function.name for function in callers)
            for function in callers:
                if caller_counts[function.name] == 1:
                    symbol_id = f'{module}.{function.name}'
                    self.callers[symbol_id] = Symbol(symbol_id, module, function.name, relative_path, function)

        for module, relative_path in self.modules.items():
            parsed = parsed_by_path[relative_path]
            self.bindings[module] = {}
            if parsed.diagnostics:
                continue
            local_functions = {function.name for function in parsed.functions}
            for imported in parsed.imports:
                binding = self._bind(module, relative_path, imported)
                if binding.local_name in local_functions:
                    binding = self._unresolved(binding, "local_name_conflict")
                if binding.local_name in self.bindings[module]:
                    binding = self._unresolved(binding, "duplicate_local_binding")
                self.bindings[module][binding.local_name] = binding
        return self

    def module_name(self, relative_path: Path) -> str:
        return module_name(relative_path, self.analysis_root)

    def unsupported_scope_diagnostics(self) -> list[dict]:
        labels = {"class_body": "类定义体", "nested_function": "嵌套函数", "lambda": "匿名函数"}
        return [
            {"code": "unsupported_call_scope", "file": file.as_posix(),
             "line": scope.line, "column": scope.column, "scope": scope.scope,
             "name": scope.name, "excluded_call_count": scope.call_count,
             "message": f"{labels[scope.scope]}中的 {scope.call_count} 个调用未进入当前函数分析范围，请人工检查。"}
            for file, parsed in sorted(self.parsed_files.items())
            for scope in parsed.unsupported_call_scopes
        ]

    def _package_problem(self, package: str) -> str | None:
        for depth in range(1, len(package.split(".")) + 1):
            name = ".".join(package.split(".")[:depth])
            if name in self.ambiguous_modules:
                return "ambiguous_project_module"
            path = self.modules.get(name)
            if path is None or path.name != "__init__.py":
                return "namespace_package_unsupported"
            if path in self.parse_diagnostics:
                return "module_parse_failed"
            if "__path__" in self.parsed_modules[name].module_rebindings:
                return "package_path_rebound"
        return None

    def _relative_module(self, source_module: str, source_file: Path,
                         imported: ImportReference) -> tuple[str | None, str | None]:
        if {"__package__", "__spec__"} & self.parsed_modules[source_module].module_rebindings:
            return None, "package_context_rebound"
        package = source_module if source_file.name == "__init__.py" else source_module.rpartition(".")[0]
        if not package:
            return None, "relative_import_without_package"
        problem = self._package_problem(package)
        if problem:
            return None, problem
        parts = package.split(".")
        if imported.level > len(parts):
            return None, "relative_import_beyond_package"
        base = ".".join(parts[:len(parts) - imported.level + 1])
        target = f"{base}.{imported.module}" if imported.module else base
        parent = target.rpartition(".")[0]
        problem = self._package_problem(parent) if parent else None
        return (None, problem) if problem else (target, None)

    @staticmethod
    def _unresolved(binding: ImportBinding, reason: str) -> ImportBinding:
        return ImportBinding(
            binding.source_module,
            binding.local_name,
            binding.source_file,
            binding.lineno,
            "unresolved",
            reason=reason,
        )

    def _module_reason(self, module: str) -> str | None:
        parts = module.split(".")
        for depth in range(1, len(parts)):
            parent = ".".join(parts[:depth])
            if parent in self.ambiguous_modules:
                return "ambiguous_project_module"
            path = self.modules.get(parent)
            if path is not None and path.name != "__init__.py":
                return "parent_module_is_not_package"
            if path is not None and path.name == "__init__.py":
                if path in self.parse_diagnostics:
                    return "module_parse_failed"
                if "__path__" in self.parsed_modules[parent].module_rebindings:
                    return "package_path_rebound"
        if module in self.ambiguous_modules:
            return "ambiguous_project_module"
        if module not in self.modules:
            return "module_not_in_project"
        if self.modules[module] in self.parse_diagnostics:
            return "module_parse_failed"
        if self.modules[module].name == "__init__.py":
            return self._package_problem(module)
        return None

    def _bind(self, source_module: str, source_file: Path, imported: ImportReference) -> ImportBinding:
        imported_module = imported.module or ""
        local_name = imported.alias or (
            imported_module.split(".")[0]
            if imported.import_type == "import"
            else imported.imported_name or ""
        )
        binding = ImportBinding(source_module, local_name, source_file, imported.lineno,
                                "unresolved")
        if imported.level:
            imported_module, reason = self._relative_module(source_module, source_file, imported)
            if reason:
                return self._unresolved(binding, reason)
        if imported.imported_name == "*":
            return self._unresolved(binding, "wildcard_import_unsupported")

        if imported.import_type == "import":
            target = imported_module if imported.alias else imported_module.split(".")[0]
            # The entire dotted import must be internal before binding its root.
            reason = self._module_reason(imported_module) or self._module_reason(target)
            if reason:
                return self._unresolved(binding, reason)
            return ImportBinding(source_module, local_name, source_file, imported.lineno,
                                 "resolved", "module", target_module=target)

        reason = self._module_reason(imported_module)
        if reason:
            return self._unresolved(binding, reason)
        symbol_id = f"{imported_module}.{imported.imported_name}"
        if symbol_id in self.ambiguous_symbols:
            return self._unresolved(binding, "ambiguous_project_symbol")
        if symbol_id in self.symbols:
            return ImportBinding(source_module, local_name, source_file, imported.lineno,
                                 "resolved", "function", imported_module, symbol_id)
        if symbol_id in self.modules and not self._module_reason(symbol_id):
            package = self.parsed_modules[imported_module]
            member = imported.imported_name
            if member in package.module_rebindings or any(
                (item.alias or (item.module.split(".")[0] if item.import_type == "import" else item.imported_name)) == member
                for item in package.imports if item is not imported
            ):
                return self._unresolved(binding, "package_member_not_proven")
            return ImportBinding(source_module, local_name, source_file, imported.lineno,
                                 "resolved", "module", target_module=symbol_id)
        return self._unresolved(binding, "name_not_in_project_module")
