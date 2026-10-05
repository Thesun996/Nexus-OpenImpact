"""Run the local OpenImpact analysis demo from the command line."""

import argparse
import json
import sys
from pathlib import Path

from openimpact.analysis.change_file import ChangeFileError, load_change_spec
from openimpact.analysis.pipeline import analyze_project
from openimpact.analysis.report import build_report, render_chinese_report
from openimpact.analysis.change_domain import read_cli_domain
from openimpact.analysis.module_change import ModuleChangeError, build_module_change
from openimpact.analysis.module_facts import ModuleInventory
from openimpact.analysis.module_pipeline import analyze_module_project
from openimpact.analysis.module_report import build_module_report, render_module_report
from openimpact.analysis.symbol_index import SymbolIndex
from openimpact.analysis.variable_symbols import VariableInventory
from openimpact.analysis.symbol_change import build_symbol_change, SymbolChangeError
from openimpact.analysis.symbol_impact import analyze_symbol_project
from openimpact.analysis.symbol_report import build_symbol_report, render_symbol_report
from openimpact.api_change import ChangeConfigError
from openimpact.repository.layout import AnalysisRootError, layout_metadata


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="openimpact")
    commands = parser.add_subparsers(dest="command", required=True)
    analyze = commands.add_parser("analyze", help="分析本地 Python 项目的结构化签名变化")
    analyze.add_argument("project_path", type=Path, help="本地 Python 项目目录")
    analyze.add_argument("--change", required=True, type=Path, help="ChangeSpec JSON 文件")
    analyze.add_argument("--format", choices=("text", "json"), default="text",
                         help="终端报告格式（默认 text）")
    analyze.add_argument("--analysis-root", default=".", help="项目内源码搜索根目录，例如 src；默认项目根目录")
    args = parser.parse_args(argv)

    try:
        domain, config = read_cli_domain(args.change)
        if domain == "symbol":
            index = SymbolIndex(args.project_path, analysis_root=args.analysis_root).build()
            inventory = VariableInventory.from_index(index)
            report = build_symbol_report(analyze_symbol_project(index, build_symbol_change(inventory, config), inventory))
            if index.analysis_root != ".":
                report["analysis_layout"] = layout_metadata(index.analysis_root)
            print(json.dumps(report, ensure_ascii=False, indent=2) if args.format == "json" else render_symbol_report(report))
            return 0
        if domain == "module":
            index = SymbolIndex(args.project_path, analysis_root=args.analysis_root).build()
            inventory = ModuleInventory.from_index(index)
            spec = build_module_change(inventory, config)
            report = build_module_report(analyze_module_project(index, spec, inventory))
            if index.analysis_root != ".":
                report["analysis_layout"] = layout_metadata(index.analysis_root)
            print(json.dumps(report, ensure_ascii=False, indent=2) if args.format == "json" else render_module_report(report))
            return 0
        spec = load_change_spec(args.change)
        run = analyze_project(args.project_path, spec, analysis_root=args.analysis_root)
    except (AnalysisRootError, ChangeFileError, ChangeConfigError, ModuleChangeError, SymbolChangeError, OSError, UnicodeError) as error:
        print(f"OpenImpact 错误：{error}", file=sys.stderr)
        return 2

    report = build_report(run)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_chinese_report(report))
    return 0 if run.direct.validation.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
