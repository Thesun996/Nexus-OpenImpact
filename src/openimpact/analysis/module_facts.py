"""Project-relative, immutable module inventory for the flat-root domain."""

import hashlib
import keyword
import sys
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path

from openimpact.analysis.symbol_index import SymbolIndex, _module_name


def normalized_name(name: str) -> str:
    return unicodedata.normalize("NFKC", name).casefold()


def name_problem(name: object) -> str | None:
    if not isinstance(name, str) or not name.isidentifier() or keyword.iskeyword(name):
        return "invalid_module_name"
    if len((name + ".py").encode("utf-8")) > 255:
        return "module_name_too_long"
    if unicodedata.normalize("NFKC", name) != name:
        return "non_normalized_module_name"
    reserved = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(10)),
                *(f"lpt{i}" for i in range(10))}
    if name.casefold() in reserved or name.casefold() in {"__init__", "__main__"}:
        return "special_module_unsupported"
    if name.casefold() in {item.casefold() for item in (*sys.stdlib_module_names, *sys.builtin_module_names)}:
        return "standard_library_name_collision"
    return None


@dataclass(frozen=True)
class ModuleDescriptor:
    module_id: str
    file: str
    source_hash: str
    parse_status: str
    selectable: bool
    reason: str | None
    kind: str


@dataclass(frozen=True)
class ModuleInventory:
    modules: tuple[ModuleDescriptor, ...]
    occupied_names: tuple[str, ...]
    analysis_scope: str = "project_root_static"

    @classmethod
    def from_index(cls, index: SymbolIndex, occupied_names: tuple[str, ...] = ()):
        paths = index.scanner.scan()
        counts: dict[str, int] = {}
        for path in paths:
            key = normalized_name(_module_name(path))
            counts[key] = counts.get(key, 0) + 1
        descriptors = []
        for path in paths:
            module = _module_name(path)
            kind = "package" if path.stem == "__init__" else "nested" if len(path.parts) != 1 else "module"
            reason = "unsupported_module_layout" if kind != "module" else name_problem(module)
            if counts[normalized_name(module)] > 1 or module in index.ambiguous_modules:
                reason = "ambiguous_module"
            parsed = path not in index.parse_diagnostics
            if not parsed:
                reason = "module_parse_failed"
            try:
                digest = hashlib.sha256((index.scanner.project_path / path).read_bytes()).hexdigest()
            except OSError:
                digest, parsed, reason = "", False, "module_source_unavailable"
            descriptors.append(ModuleDescriptor(
                module, path.as_posix(), digest,
                "ok" if parsed else "error", reason is None, reason, kind,
            ))
        # Include directories and non-Python entries for local CLI name conflicts.
        names = {entry.stem if entry.suffix.casefold() == ".py" else entry.name
                 for entry in index.scanner.project_path.iterdir()}
        return cls(tuple(descriptors), tuple(sorted(names | set(occupied_names))))

    def get(self, module_id: str) -> ModuleDescriptor | None:
        found = [module for module in self.modules if module.module_id == module_id]
        return found[0] if len(found) == 1 else None

    def to_dict(self) -> dict:
        return {"analysis_scope": self.analysis_scope, "modules": [asdict(m) for m in self.modules],
                "occupied_names": list(self.occupied_names)}
