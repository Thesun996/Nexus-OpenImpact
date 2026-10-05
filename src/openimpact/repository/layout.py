"""Explicit, project-relative Python import roots; never evaluate build scripts."""

from pathlib import Path, PurePosixPath
import stat


class AnalysisRootError(ValueError):
    code = "invalid_analysis_root"


def validate_analysis_root(project_path: Path, analysis_root: str | None) -> str:
    root = "." if analysis_root is None else analysis_root
    if not isinstance(root, str) or not root or len(root) > 255:
        raise AnalysisRootError("源码根目录必须是项目内的相对目录，项目根目录使用 '.'。")
    if root == ".":
        return root
    parts = root.split("/")
    reserved = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(10)),
                *(f"lpt{i}" for i in range(10))}
    if (PurePosixPath(root).is_absolute() or "\\" in root
            or any(part in {"", ".", ".."} or part.endswith((".", " "))
                   or any(ord(c) < 32 or c in ':*?"<>|' for c in part)
                   or part.split(".")[0].casefold() in reserved for part in parts)):
        raise AnalysisRootError("源码根目录须使用项目内相对路径，不能包含绝对路径或路径跳转。")
    current = project_path
    for part in parts:
        current /= part
        try:
            info = current.lstat()
        except OSError as error:
            raise AnalysisRootError("项目中没有指定的源码根目录。") from error
        if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
                or getattr(info, "st_file_attributes", 0)
                & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)):
            raise AnalysisRootError("源码根目录必须是普通目录，不能使用链接或特殊文件。")
    if not current.resolve().is_relative_to(project_path.resolve()):
        raise AnalysisRootError("源码根目录必须位于本次项目中。")
    if (current / "__init__.py").exists():
        raise AnalysisRootError("请选择 Python 包的父目录作为源码根目录，包自身含有 __init__.py。")
    return root


def module_name(relative_file: Path, analysis_root: str = ".") -> str:
    path = relative_file
    if analysis_root != "." and path.is_relative_to(Path(analysis_root)):
        path = path.relative_to(analysis_root)
    parts = path.with_suffix("").parts
    if parts[-1] == "__init__" and len(parts) > 1:
        parts = parts[:-1]
    return ".".join(parts)


def layout_metadata(analysis_root: str) -> dict:
    return {"analysis_root": analysis_root, "mode": "explicit",
            "import_roots": [".", analysis_root] if analysis_root != "." else ["."]}
