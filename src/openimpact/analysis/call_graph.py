"""Create only statically resolved caller-context to module-function edges."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from openimpact.analysis.models import CallScope, FunctionCall, FunctionDefinition
from openimpact.analysis.symbol_index import SymbolIndex

ResolutionBasis = Literal["same_module", "from_import", "module_import"]


@dataclass(frozen=True)
class CallEdge:
    caller_symbol_id: str
    callee_symbol_id: str
    file: Path
    line: int
    col_offset: int
    status: Literal["resolved"]
    basis: ResolutionBasis


@dataclass(frozen=True)
class UnresolvedCall:
    caller_symbol_id: str | None
    file: Path
    line: int
    call: FunctionCall
    reason: str


class CallGraph:
    """Resolve supported call syntax using an already built SymbolIndex."""

    def __init__(self, index: SymbolIndex):
        self.index = index
        self.edges: set[CallEdge] = set()
        self.unresolved_calls: list[UnresolvedCall] = []

    def build(self) -> "CallGraph":
        self.edges.clear()
        self.unresolved_calls.clear()
        seen_unresolved: set[tuple[Path, int, int, str]] = set()
        for module, relative_path in self.index.modules.items():
            parsed = self.index.parsed_modules[module]
            for call in parsed.calls:
                caller_id = (
                    f"{module}.{call.enclosing_function}"
                    if call.enclosing_function is not None else None
                )
                reason: str | None = None
                if caller_id is None:
                    reason = "module_level_call"
                elif caller_id not in self.index.callers:
                    reason = "caller_not_indexed"
                else:
                    callee_id, basis, reason = self._resolve(module, caller_id, call)
                    if callee_id is not None and basis is not None:
                        self.edges.add(
                            CallEdge(caller_id, callee_id, relative_path, call.lineno,
                                     call.col_offset, "resolved", basis)
                        )
                        continue
                key = (relative_path, call.lineno, call.col_offset, call.expression)
                if key not in seen_unresolved:
                    self.unresolved_calls.append(
                        UnresolvedCall(caller_id, relative_path, call.lineno, call,
                                       reason or "unknown_target")
                    )
                    seen_unresolved.add(key)
        return self

    def _resolve(
        self, module: str, caller_id: str, call: FunctionCall
    ) -> tuple[str | None, ResolutionBasis | None, str | None]:
        if call.callee_path is None:
            return None, None, "unsupported_callee_expression"
        path = call.callee_path
        root = path[0]
        definition = self.index.callers[caller_id].definition
        if isinstance(definition, CallScope) and definition.namespace_uncertain:
            return None, None, 'class_namespace_unresolved'
        if root in definition.local_bindings or isinstance(definition, FunctionDefinition) and any(
            parameter.name == root for parameter in definition.parameters
        ):
            return None, None, "local_name_shadows_target"
        if root in self.index.parsed_modules[module].module_rebindings:
            return None, None, "module_name_rebound"

        binding = self.index.bindings[module].get(root)
        if isinstance(definition, CallScope) and definition.module_evaluation:
            # Class bodies/defaults run during definition, unlike a deferred
            # function body. A later import/definition cannot justify that call.
            local_target = self.index.symbols.get(f'{module}.{root}')
            if binding is not None and binding.lineno > call.lineno or (
                binding is None and local_target is not None
                and local_target.definition.lineno > call.lineno
            ):
                return None, None, 'call_before_binding'

        if len(path) > 2:
            if binding is None or binding.status != 'resolved' or binding.kind != 'module':
                return None, None, 'attribute_chain_unsupported'
            target_module = '.'.join((binding.target_module, *path[1:-1]))
            # An uploaded child file alone does not prove pkg.child is exposed.
            # Only an explicit dotted import proves this supported attribute chain.
            explicit = any(item.import_type == 'import' and item.alias is None
                and (item.module == target_module or item.module.startswith(target_module + '.'))
                for item in self.index.parsed_modules[module].imports)
            target = f'{target_module}.{path[-1]}'
            if explicit and not self.index._module_reason(target_module) and target in self.index.symbols:
                if self._dotted_path_is_rebound(module, binding.target_module, path):
                    return None, None, 'attribute_chain_unsupported'
                if self._callee_is_rebound(target):
                    return None, None, 'callee_module_name_rebound'
                return target, 'module_import', None
            return None, None, 'attribute_chain_unsupported'

        if len(path) == 1:
            if binding is not None:
                if binding.status != "resolved":
                    return None, None, "import_binding_unresolved"
                if binding.kind == "function" and binding.target_symbol_id in self.index.symbols:
                    if self._callee_is_rebound(binding.target_symbol_id):
                        return None, None, "callee_module_name_rebound"
                    return binding.target_symbol_id, "from_import", None
                return None, None, "module_used_as_function"
            target = f"{module}.{root}"
            if target in self.index.symbols:
                if self._callee_is_rebound(target):
                    return None, None, "callee_module_name_rebound"
                return target, "same_module", None
            return None, None, "name_not_indexed"

        if binding is None:
            return None, None, "module_binding_missing"
        if binding.status != "resolved":
            return None, None, "import_binding_unresolved"
        if binding.kind != "module" or binding.target_module is None:
            return None, None, "attribute_root_not_module"
        target = f"{binding.target_module}.{path[1]}"
        if target in self.index.symbols:
            if self._callee_is_rebound(target):
                return None, None, "callee_module_name_rebound"
            return target, "module_import", None
        return None, None, "attribute_target_not_indexed"

    def _dotted_path_is_rebound(self, module: str, root_module: str, path: tuple[str, ...]) -> bool:
        parsed = self.index.parsed_modules[module]
        if any(path[:len(written)] == written for written in parsed.attribute_rebindings):
            return True
        parts = (root_module, *path[1:-1])
        for depth in range(1, len(parts)):
            parent = self.index.parsed_modules.get('.'.join(parts[:depth]))
            if parent is not None and parts[depth] in parent.module_rebindings:
                return True
        return False

    def _callee_is_rebound(self, symbol_id: str) -> bool:
        symbol = self.index.symbols[symbol_id]
        return symbol.qualified_name in self.index.parsed_modules[symbol.module].module_rebindings
