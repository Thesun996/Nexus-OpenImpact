"""Index project modules and functions, then bind explicit local imports."""

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from openimpact.analysis.ast_parser import ASTParser
from openimpact.analysis.models import (
    FunctionDefinition,
    ImportReference,
    ParseDiagnostic,
    ParsedModule,
)
from openimpact.repository.scanner import RepositoryScanner


@dataclass(frozen=True)
class Symbol:
    symbol_id: str
    module: str
    qualified_name: str
    file: Path
    definition: FunctionDefinition


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
    parts = relative_path.with_suffix("").parts
    if parts[-1] == "__init__" and len(parts) > 1:
        parts = parts[:-1]
    return ".".join(parts)


class SymbolIndex:
    """Project-level identity map; it never inspects or resolves calls."""

    def __init__(self, project_path: str | Path):
        self.scanner = RepositoryScanner(project_path)
        self.modules: dict[str, Path] = {}
        self.symbols: dict[str, Symbol] = {}
        self.bindings: dict[str, dict[str, ImportBinding]] = {}
        self.parsed_modules: dict[str, ParsedModule] = {}
        self.parse_diagnostics: dict[Path, tuple[ParseDiagnostic, ...]] = {}
        self.ambiguous_modules: set[str] = set()
        self.ambiguous_symbols: set[str] = set()

    def build(self) -> "SymbolIndex":
        self.modules.clear()
        self.symbols.clear()
        self.bindings.clear()
        self.parsed_modules.clear()
        self.parse_diagnostics.clear()
        self.ambiguous_modules.clear()
        self.ambiguous_symbols.clear()

        paths_by_module: dict[str, list[Path]] = defaultdict(list)
        parsed_by_path: dict[Path, ParsedModule] = {}
        for relative_path in self.scanner.scan():
            module = _module_name(relative_path)
            paths_by_module[module].append(relative_path)
            parsed = ASTParser(self.scanner.project_path / relative_path).parse()
            parsed_by_path[relative_path] = parsed
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
        if module in self.ambiguous_modules:
            return "ambiguous_project_module"
        if module not in self.modules:
            return "module_not_in_project"
        if self.modules[module] in self.parse_diagnostics:
            return "module_parse_failed"
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
            return self._unresolved(binding, "relative_import_unsupported")
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
            return ImportBinding(source_module, local_name, source_file, imported.lineno,
                                 "resolved", "module", target_module=symbol_id)
        return self._unresolved(binding, "name_not_in_project_module")
