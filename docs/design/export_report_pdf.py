#!/usr/bin/env python3
"""Render a Markdown design report to a formatted A4 PDF via LibreOffice.

This is an artifact-generation script, not a source-file editing shortcut.
Requires the `markdown` Python package and LibreOffice Writer.
"""

from __future__ import annotations

import html
import subprocess
import sys
import tempfile
from pathlib import Path

import markdown


STYLE = """
@page { size: A4; margin: 18mm; }
body { font-family: 'DejaVu Sans', Arial, sans-serif; font-size: 10pt;
       line-height: 1.35; color: #1e293b; }
h1 { font-size: 21pt; color: #0b5cad; }
h2 { font-size: 14pt; color: #0b5cad; margin-top: 18pt; }
table { border-collapse: collapse; width: 100%; font-size: 8.5pt; }
th, td { border: 1px solid #cbd5e1; padding: 5pt; vertical-align: top; }
th { background: #e8f2fd; }
code { font-family: 'DejaVu Sans Mono', monospace; font-size: 8pt; }
pre { background: #f3f6fa; padding: 8pt; white-space: pre-wrap; }
a { color: #0b5cad; }
"""


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: export_report_pdf.py REPORT.md")
    source = Path(sys.argv[1]).resolve()
    output_dir = source.parent
    body = markdown.markdown(
        source.read_text(encoding="utf-8"),
        extensions=["tables", "fenced_code", "toc"],
    )
    document = (
        '<!DOCTYPE html><html lang="vi"><head><meta charset="utf-8"><title>'
        + html.escape(source.stem)
        + '</title><style>' + STYLE + '</style></head><body>' + body + '</body></html>'
    )
    with tempfile.TemporaryDirectory(prefix="aims-report-") as temporary:
        temp = Path(temporary)
        html_path = temp / f"{source.stem}.html"
        html_path.write_text(document, encoding="utf-8")
        subprocess.run(
            ["libreoffice", f"-env:UserInstallation=file://{temp / 'lo-profile'}", "--headless",
             "--convert-to", "pdf:writer_pdf_Export", "--outdir", str(output_dir), str(html_path)],
            check=True,
        )
    print(output_dir / f"{source.stem}.pdf")


if __name__ == "__main__":
    main()
