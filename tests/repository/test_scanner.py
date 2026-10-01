"""Repository discovery checks using temporary directories only."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from openimpact.repository.scanner import RepositoryScanner


class RepositoryScannerTests(unittest.TestCase):
    def setUp(self):
        self.workspace = TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.root = Path(self.workspace.name) / "project"
        self.root.mkdir()

    def create_file(self, relative_path):
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
        return path

    def test_requested_project_returns_only_python_sources(self):
        for name in (
            "main.py", "utils.py", "README.md",
            ".venv/fake.py", "node_modules/test.py",
        ):
            self.create_file(name)

        self.assertEqual(
            RepositoryScanner(self.root).scan(),
            [Path("main.py"), Path("utils.py")],
        )

    def test_nested_sources_are_sorted_and_all_ignored_directories_are_pruned(self):
        ignored = (".git", ".venv", "__pycache__", "node_modules", "dist", "build")
        for directory in ignored:
            self.create_file(f"{directory}/fake.py")
            self.create_file(f"package/{directory}/fake.py")
        for name in ("z.py", "package/utils.py", "package/__init__.py", "a.py"):
            self.create_file(name)
        self.create_file("package/module.py.txt")
        self.create_file("build_helpers/keep.py")
        self.root.joinpath("empty.py").mkdir()

        expected = [
            Path("a.py"), Path("build_helpers/keep.py"),
            Path("package/__init__.py"), Path("package/utils.py"), Path("z.py"),
        ]
        scanner = RepositoryScanner(str(self.root))
        self.assertEqual(scanner.scan(), expected)
        self.assertEqual(scanner.scan(), expected)

    def test_empty_project_returns_empty_list(self):
        self.assertEqual(RepositoryScanner(self.root).scan(), [])

    def test_invalid_project_path_raises(self):
        with self.assertRaises(FileNotFoundError):
            RepositoryScanner(self.root / "missing")
        with self.assertRaises(NotADirectoryError):
            RepositoryScanner(self.create_file("main.py"))

    def test_scan_does_not_read_or_execute_source(self):
        self.create_file("main.py").write_text(
            "raise RuntimeError('must never execute')", encoding="utf-8"
        )
        self.create_file("invalid.py").write_bytes(b"\xff\xfe\x00")
        self.assertEqual(
            RepositoryScanner(self.root).scan(),
            [Path("invalid.py"), Path("main.py")],
        )

    def test_symbolic_links_are_skipped(self):
        outside = self.root.parent / "outside"
        outside.mkdir()
        (outside / "external.py").write_text("", encoding="utf-8")
        try:
            (self.root / "linked.py").symlink_to(outside / "external.py")
            (self.root / "linked_dir").symlink_to(outside, target_is_directory=True)
            (self.root / "loop").symlink_to(self.root, target_is_directory=True)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"Symbolic links unavailable: {error}")
        self.create_file("main.py")
        self.assertEqual(RepositoryScanner(self.root).scan(), [Path("main.py")])

    @unittest.skipUnless(os.name == "nt", "Windows junction check")
    def test_windows_junction_is_skipped(self):
        import _winapi

        outside = self.root.parent / "outside"
        outside.mkdir()
        (outside / "external.py").write_text("", encoding="utf-8")
        junction = self.root / "linked_dir"
        _winapi.CreateJunction(str(outside), str(junction))
        self.addCleanup(junction.rmdir)
        self.create_file("main.py")
        self.assertEqual(RepositoryScanner(self.root).scan(), [Path("main.py")])


if __name__ == "__main__":
    unittest.main()
