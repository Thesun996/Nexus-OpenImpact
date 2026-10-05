"""Bounded extraction and syntax-only inspection of an untrusted Python ZIP."""

import hashlib
import io
import stat
import struct
import zipfile
import zlib
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory

from openimpact.analysis.symbol_index import SymbolIndex
from openimpact.analysis.module_facts import ModuleInventory
from openimpact.analysis.import_resolver import resolve_imports
from openimpact.analysis.module_report import module_coverage, module_diagnostics
from openimpact.repository.scanner import RepositoryScanner

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_ENTRIES = 256
MAX_FILES = 128
MAX_FILE_BYTES = 1 * 1024 * 1024
MAX_TOTAL_BYTES = 10 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200
_CHUNK_BYTES = 64 * 1024
_SUPPORTED_COMPRESSION = frozenset({zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED})
_WINDOWS_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(10)),
     *(f"LPT{i}" for i in range(10))}
)


class ZipInspectionError(ValueError):
    def __init__(self, code: str, message: str, status_code: int):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def _reject(code: str, message: str, status_code: int = 400) -> None:
    raise ZipInspectionError(code, message, status_code)


def _entry_parts(info: zipfile.ZipInfo) -> tuple[str, ...]:
    name = info.filename
    if (
        not name or len(name) > 512 or name.startswith("/") or "\\" in name
        or any(ord(char) < 32 or ord(char) == 127 or char in '<>:"|?*' for char in name)
    ):
        _reject("unsafe_zip_entry", "ZIP 包含绝对路径、Windows 特殊路径或非法文件名。")
    raw = name[:-1] if info.is_dir() else name
    parts = tuple(raw.split("/"))
    if any(
        not part or part in {".", ".."} or part.endswith((".", " "))
        or part.split(".", 1)[0].upper() in _WINDOWS_RESERVED
        for part in parts
    ):
        _reject("unsafe_zip_entry", "ZIP 包含目录穿越、空路径段或 Windows 保留名称。")

    mode = (info.external_attr >> 16) & 0xFFFF
    kind = stat.S_IFMT(mode)
    if kind not in (0, stat.S_IFDIR if info.is_dir() else stat.S_IFREG):
        _reject("unsafe_zip_entry", "ZIP 包含符号链接或其他特殊文件。")
    if info.flag_bits & 0x1:
        _reject("unsupported_zip_entry", "暂不支持加密 ZIP 条目。", 415)
    if info.compress_type not in _SUPPORTED_COMPRESSION:
        _reject("unsupported_zip_entry", "ZIP 包含不支持的压缩方法。", 415)
    return parts


def _check_raw_names(archive: zipfile.ZipFile, data: bytes, count: int) -> None:
    """Check central names before ZipInfo can normalize Windows separators."""
    offset = archive.start_dir
    for _ in range(count):
        if offset < 0 or offset + 46 > len(data) or data[offset:offset + 4] != b"PK\x01\x02":
            _reject("invalid_zip", "ZIP 中央目录损坏。")
        name_length, extra_length, comment_length = struct.unpack_from("<HHH", data, offset + 28)
        end = offset + 46 + name_length + extra_length + comment_length
        if end > len(data):
            _reject("invalid_zip", "ZIP 中央目录损坏。")
        raw_name = data[offset + 46:offset + 46 + name_length]
        if b"\\" in raw_name or b"\x00" in raw_name:
            _reject("unsafe_zip_entry", "ZIP 包含 Windows 路径分隔符或非法文件名。")
        offset = end


def _inspect_entries(
    archive: zipfile.ZipFile, data: bytes
) -> list[tuple[zipfile.ZipInfo, tuple[str, ...]]]:
    entries = archive.infolist()
    if len(entries) > MAX_ENTRIES:
        _reject("zip_limit_exceeded", "ZIP 条目数量超过限制。", 413)
    _check_raw_names(archive, data, len(entries))
    validated: list[tuple[zipfile.ZipInfo, tuple[str, ...]]] = []
    seen: set[tuple[str, ...]] = set()
    file_paths: set[tuple[str, ...]] = set()
    file_count = 0
    total_size = 0
    for info in entries:
        # On Windows ZipInfo normalizes backslashes to '/'. Inspect the original
        # local-header name so this normalization cannot hide a dangerous path.
        offset = info.header_offset
        if offset < 0 or offset + 30 > len(data) or data[offset:offset + 4] != b"PK\x03\x04":
            _reject("invalid_zip", "ZIP 文件头损坏。")
        name_length, _ = struct.unpack_from("<HH", data, offset + 26)
        raw_name = data[offset + 30:offset + 30 + name_length]
        if len(raw_name) != name_length or b"\\" in raw_name or b"\x00" in raw_name:
            _reject("unsafe_zip_entry", "ZIP 包含 Windows 路径分隔符或非法文件名。")
        parts = _entry_parts(info)
        folded = tuple(part.casefold() for part in parts)
        if folded in seen:
            _reject("unsafe_zip_entry", "ZIP 包含重复或大小写冲突的路径。")
        seen.add(folded)
        if not info.is_dir():
            file_count += 1
            total_size += info.file_size
            file_paths.add(folded)
            if file_count > MAX_FILES or info.file_size > MAX_FILE_BYTES or total_size > MAX_TOTAL_BYTES:
                _reject("zip_limit_exceeded", "ZIP 文件数量或解压大小超过限制。", 413)
            if info.file_size > max(info.compress_size, 1) * MAX_COMPRESSION_RATIO:
                _reject("zip_limit_exceeded", "ZIP 条目的压缩比超过限制。", 413)
        validated.append((info, parts))
    for path in seen:
        if any(path[:index] in file_paths for index in range(1, len(path))):
            _reject("unsafe_zip_entry", "ZIP 文件与其子路径冲突。")
    return validated


def _python_entries(
    entries: list[tuple[zipfile.ZipInfo, tuple[str, ...]]],
) -> tuple[list[tuple[zipfile.ZipInfo, tuple[str, ...]]], str | None]:
    sources = [
        (info, parts) for info, parts in entries
        if not info.is_dir() and parts[-1].endswith(".py")
        and not any(part in RepositoryScanner.IGNORED_DIRECTORIES for part in parts[:-1])
    ]
    if not sources:
        _reject("no_python_files", "ZIP 中没有可分析的 Python 源文件。", 422)
    roots = {parts[0] for _, parts in sources if len(parts) > 1}
    has_root_file = any(len(parts) == 1 for _, parts in sources)
    package_root = any(len(parts) == 2 and parts[1] == "__init__.py" for _, parts in sources)
    strip_root = next(iter(roots)) if len(roots) == 1 and not has_root_file and not package_root else None
    return sources, strip_root


def _project_name(filename: str | None, stripped_root: str | None) -> str:
    if stripped_root:
        return stripped_root
    basename = (filename or "project.zip").replace("\\", "/").split("/")[-1]
    stem = basename[:-4] if basename.lower().endswith(".zip") else basename
    return stem[:100] or "uploaded-project"


def _extract_python(
    archive: zipfile.ZipFile,
    entries: list[tuple[zipfile.ZipInfo, tuple[str, ...]]],
    root: Path,
    stripped_root: str | None,
) -> None:
    total_written = 0
    for info, parts in entries:
        relative = parts[1:] if stripped_root else parts
        destination = root.joinpath(*relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        written = 0
        with archive.open(info) as source, destination.open("xb") as target:
            while chunk := source.read(_CHUNK_BYTES):
                written += len(chunk)
                total_written += len(chunk)
                if written > MAX_FILE_BYTES or total_written > MAX_TOTAL_BYTES:
                    _reject("zip_limit_exceeded", "实际解压大小超过限制。", 413)
                target.write(chunk)


def _result(
    index: SymbolIndex, filename: str | None, fingerprint: str,
    stripped_root: str | None, source_count: int, occupied_names: tuple[str, ...] = (),
) -> dict:
    def safe_message(kind: str, message: str) -> str:
        if kind == "read_error":
            return "无法读取项目源文件。"
        if kind == "encoding_error":
            return "项目源文件编码无法解析。"
        return message

    parse_errors = [
        {"file": path.as_posix(), "kind": item.kind,
         "message": safe_message(item.kind, item.message),
         "line": item.lineno, "column": item.col_offset}
        for path, diagnostics in sorted(index.parse_diagnostics.items())
        for item in diagnostics
    ]
    unresolved_imports = [
        {"file": binding.source_file.as_posix(), "line": binding.lineno,
         "local_name": binding.local_name, "reason": binding.reason}
        for module in sorted(index.bindings)
        for binding in index.bindings[module].values()
        if binding.status == "unresolved"
    ]
    symbols = [
        {"symbol_id": symbol.symbol_id, "module": symbol.module,
         "file": symbol.file.as_posix(), "name": symbol.qualified_name,
         "line": symbol.definition.lineno,
         "parameters": [asdict(parameter) for parameter in symbol.definition.parameters]}
        for _, symbol in sorted(index.symbols.items())
    ]
    modules = [
        {"module": module, "file": path.as_posix(),
         "parse_status": "error" if path in index.parse_diagnostics else "ok"}
        for module, path in sorted(index.modules.items())
    ]
    partial = bool(parse_errors or unresolved_imports or index.ambiguous_modules
                   or index.ambiguous_symbols)
    inventory = ModuleInventory.from_index(index, occupied_names)
    references = resolve_imports(index, inventory)
    from openimpact.analysis.variable_symbols import VariableInventory
    from openimpact.analysis.symbol_report import symbol_inspect
    return {
        **symbol_inspect(index, VariableInventory.from_index(index, inventory)),
        "module_inventory": inventory.to_dict(),
        "module_coverage": module_coverage(index, inventory, references),
        "module_diagnostics": module_diagnostics(index, inventory, references),
        "project_name": _project_name(filename, stripped_root),
        "project_fingerprint": fingerprint,
        "source_root": stripped_root,
        "modules": modules,
        "symbols": symbols,
        "coverage": {
            "status": "partial" if partial else "complete",
            "python_files": source_count,
            "indexed_modules": len(index.modules),
            "indexed_functions": len(index.symbols),
            "files_with_parse_errors": len(index.parse_diagnostics),
        },
        "diagnostics": {
            "parse_errors": parse_errors,
            "unresolved_imports": unresolved_imports,
            "ambiguous_modules": sorted(index.ambiguous_modules),
            "ambiguous_symbols": sorted(index.ambiguous_symbols),
        },
    }


@contextmanager
def indexed_python_zip(data: bytes, filename: str | None = None):
    """Yield the existing syntax index and inspect report inside one isolated import."""
    if len(data) > MAX_UPLOAD_BYTES:
        _reject("zip_limit_exceeded", "ZIP 上传大小超过限制。", 413)
    fingerprint = hashlib.sha256(data).hexdigest()
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, EOFError, RuntimeError, NotImplementedError, zlib.error) as error:
        _reject("invalid_zip", f"ZIP 文件损坏或无法解压：{error}")
    with archive:
        try:
            entries = _inspect_entries(archive, data)
            sources, stripped_root = _python_entries(entries)
        except (zipfile.BadZipFile, EOFError, RuntimeError, NotImplementedError, zlib.error) as error:
            _reject("invalid_zip", f"ZIP 文件损坏或无法解压：{error}")
        with TemporaryDirectory(prefix="openimpact-zip-") as temporary:
            project_root = Path(temporary) / "source"
            project_root.mkdir()
            try:
                _extract_python(archive, sources, project_root, stripped_root)
            except (zipfile.BadZipFile, EOFError, RuntimeError, NotImplementedError, zlib.error) as error:
                _reject("invalid_zip", f"ZIP 文件损坏或无法解压：{error}")
            index = SymbolIndex(project_root).build()
            # Preserve all validated root names, including unextracted directories
            # and non-Python entries, for virtual rename collision checks.
            occupied = set()
            for _, parts in entries:
                if stripped_root and parts[0] != stripped_root:
                    continue
                relative = parts[1:] if stripped_root else parts
                if relative:
                    name = relative[0]
                    occupied.add(Path(name).stem if name.casefold().endswith(".py") else name)
            yield index, _result(index, filename, fingerprint, stripped_root, len(sources), tuple(occupied))


def inspect_python_zip(data: bytes, filename: str | None = None) -> dict:
    """Return syntax facts from an untrusted ZIP, cleaning up before returning."""
    with indexed_python_zip(data, filename) as (_, report):
        return report
