"""Run the local OpenImpact analysis demo from the command line."""

import argparse
import json
import sys
from pathlib import Path

from openimpact.analysis.change_file import ChangeFileError, load_change_spec
from openimpact.analysis.pipeline import analyze_project
from openimpact.analysis.report import build_report, render_chinese_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="openimpact")
    commands = parser.add_subparsers(dest="command", required=True)
    analyze = commands.add_parser("analyze", help="分析本地 Python 项目的结构化签名变化")
    analyze.add_argument("project_path", type=Path, help="本地 Python 项目目录")
    analyze.add_argument("--change", required=True, type=Path, help="ChangeSpec JSON 文件")
    analyze.add_argument("--format", choices=("text", "json"), default="text",
                         help="终端报告格式（默认 text）")
    args = parser.parse_args(argv)

    try:
        spec = load_change_spec(args.change)
        run = analyze_project(args.project_path, spec)
    except (ChangeFileError, OSError) as error:
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
