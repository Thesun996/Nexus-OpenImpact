"""Discover Python source paths without reading or executing project code."""

from pathlib import Path
import stat


class RepositoryScanner:
    """Scan a local directory, pruning ignored directories and linked entries.

    Results are relative to ``project_path`` and sorted by POSIX path spelling.
    Filesystem errors propagate so an incomplete scan cannot look successful.
    The project tree must remain stable during scanning; this is not a sandbox
    against concurrent filesystem changes.
    """

    IGNORED_DIRECTORIES = frozenset(
        {".git", ".venv", "__pycache__", "node_modules", "dist", "build"}
    )

    def __init__(self, project_path: str | Path):
        self.project_path = Path(project_path).resolve(strict=True)
        if not self.project_path.is_dir():
            raise NotADirectoryError(f"Project path is not a directory: {self.project_path}")

    def scan(self) -> list[Path]:
        """Return regular ``.py`` files as relative Paths, without following links."""
        sources: list[Path] = []
        directories = [self.project_path]
        while directories:
            directory = directories.pop()
            for entry in directory.iterdir():
                info = entry.lstat()
                # Reparse points include Windows junctions (also on Python 3.11).
                if stat.S_ISLNK(info.st_mode) or (
                    getattr(info, "st_file_attributes", 0)
                    & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
                ):
                    continue
                if stat.S_ISDIR(info.st_mode):
                    if entry.name not in self.IGNORED_DIRECTORIES:
                        directories.append(entry)
                elif stat.S_ISREG(info.st_mode) and entry.suffix == ".py":
                    sources.append(entry.relative_to(self.project_path))
        return sorted(sources, key=lambda path: path.as_posix())
