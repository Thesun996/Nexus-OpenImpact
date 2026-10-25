"""Relation graphs retain real caller contexts and safe public diagnostics."""

import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from openimpact.analysis.models import ParseDiagnostic
from openimpact.analysis.relation_graph import build_relation_graph
from openimpact.analysis.symbol_index import SymbolIndex
from openimpact.api import app


def test_resolved_edges_include_real_caller_context_nodes_without_new_targets(tmp_path):
    (tmp_path / "a.py").write_text(
        "def target():\n    return 1\n"
        "class C:\n    value = target()\n"
        "    def method(self):\n        return target()\n"
        "def outer():\n    def inner():\n        return target()\n"
        "    return inner\n"
        "callback = lambda: target()\n"
        "class Unused:\n    def unused(self):\n        return 1\n",
        encoding="utf-8",
    )
    index = SymbolIndex(tmp_path).build()
    payload = build_relation_graph(index)
    nodes = {node["id"]: node for node in payload["graph"]["nodes"]}
    contexts = {
        "a.C.<class_body@3:0>": ("class_body", 3),
        "a.C.method": ("function", 5),
        "a.outer.<locals>.inner": ("function", 8),
        "a.<lambda@11:11>": ("lambda", 11),
    }
    assert set(nodes) == {"a.target", "a.outer", *contexts}
    for caller, (kind, line) in contexts.items():
        assert nodes[caller]["kind"] == kind
        assert nodes[caller]["file"] == "a.py"
        assert nodes[caller]["line"] == line
        assert nodes[caller]["end_line"] >= line
        assert caller not in index.symbols  # Caller contexts stay unselectable.
    assert {(edge["source"], edge["target"]) for edge in payload["graph"]["edges"]} == {
        (caller, "a.target") for caller in contexts
    }
    assert all(edge["source"] in nodes and edge["target"] in nodes
               for edge in payload["graph"]["edges"])
    assert payload["coverage"]["indexed_functions"] == 2
    assert payload["coverage"]["resolved_calls"] == 4
    assert payload["coverage"]["status"] == "complete"


@pytest.mark.parametrize("kind,message", [
    ("encoding_error", "项目源文件编码无法解析。"),
    ("read_error", "无法读取项目源文件。"),
])
def test_graph_public_diagnostics_hide_server_paths(tmp_path, kind, message):
    (tmp_path / "bad.py").write_text("def target(): pass\n", encoding="utf-8")
    index = SymbolIndex(tmp_path).build()
    index.parse_diagnostics[next(iter(index.parsed_files))] = (
        ParseDiagnostic(kind, f"server private path: {tmp_path / 'bad.py'}"),
    )
    payload = build_relation_graph(index)
    assert payload["diagnostics"]["parse_errors"] == [{
        "file": "bad.py", "kind": kind, "line": None,
        "column": None, "message": message,
    }]
    assert payload["coverage"]["status"] == "partial"


def test_graph_and_inspect_use_identical_safe_encoding_diagnostics():
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr("bad.py", "# coding: not-an-encoding\ndef target(): pass\n")
    upload = {"file": ("project.zip", data.getvalue(), "application/zip")}
    with TestClient(app) as client:
        graph = client.post("/api/v1/projects/graph", files=upload)
        inspection = client.post("/api/v1/projects/inspect", files=upload)
    assert graph.status_code == inspection.status_code == 200
    assert graph.json()["diagnostics"]["parse_errors"] == inspection.json()["diagnostics"]["parse_errors"]
    assert "openimpact-zip-" not in graph.text
    assert graph.json()["coverage"]["status"] == "partial"
