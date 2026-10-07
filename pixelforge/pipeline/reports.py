"""
PixelForge - Report Export
=============================

Turns a CompressionReport (or a list of BatchResult) into JSON, CSV or a
self-contained HTML report the user can open in a browser or attach to an
email / ticket.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import asdict
from typing import Iterable


def report_to_json(report) -> str:
    d = asdict(report) if not isinstance(report, dict) else report
    return json.dumps(d, indent=2, default=str)


def batch_to_json(results: Iterable) -> str:
    out = []
    for r in results:
        item = {"input_path": r.input_path, "error": r.error, "kept_original": r.kept_original}
        if r.report:
            item.update(asdict(r.report))
        out.append(item)
    return json.dumps(out, indent=2, default=str)


def batch_to_csv(results: Iterable) -> str:
    buf = io.StringIO()
    fieldnames = ["input_path", "output_path", "original_format", "output_format",
                  "original_size", "final_size", "saved_bytes", "reduction_percent",
                  "estimated_quality", "ssim", "psnr", "encoding_time", "error", "kept_original"]
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for r in results:
        row = {"input_path": r.input_path, "error": r.error or "", "kept_original": r.kept_original}
        if r.report:
            rep = r.report
            row.update({
                "output_path": rep.output_path, "original_format": rep.original_format,
                "output_format": rep.output_format, "original_size": rep.original_size,
                "final_size": rep.final_size, "saved_bytes": rep.saved_bytes,
                "reduction_percent": rep.reduction_percent, "estimated_quality": rep.estimated_quality,
                "ssim": rep.ssim, "psnr": rep.psnr, "encoding_time": rep.encoding_time,
            })
        writer.writerow(row)
    return buf.getvalue()


_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>PixelForge Compression Report</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;background:#0f1115;color:#e6e6e6;padding:24px}}
h1{{color:#4fd1c5}} table{{border-collapse:collapse;width:100%;margin-top:16px}}
th,td{{border:1px solid #2a2e37;padding:8px 10px;text-align:left;font-size:13px}}
th{{background:#1a1d24;color:#4fd1c5}} tr:nth-child(even){{background:#161922}}
.summary{{display:flex;gap:24px;margin:16px 0;flex-wrap:wrap}}
.card{{background:#1a1d24;border:1px solid #2a2e37;border-radius:10px;padding:14px 18px;min-width:160px}}
.card b{{display:block;font-size:20px;color:#4fd1c5}}
.ok{{color:#57d68d}} .bad{{color:#ff6b6b}}
</style></head><body>
<h1>PixelForge Compression Report</h1>
<div class="summary">
  <div class="card"><b>{n_files}</b>Files processed</div>
  <div class="card"><b>{total_saved}</b>Bytes saved</div>
  <div class="card"><b>{avg_reduction:.1f}%</b>Avg. reduction</div>
  <div class="card"><b>{n_errors}</b>Errors</div>
</div>
<table>
<tr><th>File</th><th>In → Out</th><th>Original</th><th>Final</th><th>Saved</th><th>Reduction</th><th>Quality</th><th>SSIM</th><th>Status</th></tr>
{rows}
</table>
</body></html>"""


def batch_to_html(results: Iterable) -> str:
    results = list(results)
    rows = []
    total_saved = 0
    reductions = []
    n_errors = 0
    for r in results:
        if r.report:
            rep = r.report
            total_saved += rep.saved_bytes
            reductions.append(rep.reduction_percent)
            status = "<span class='ok'>kept original</span>" if r.kept_original else "<span class='ok'>OK</span>"
            rows.append(
                f"<tr><td>{rep.original_path}</td><td>{rep.original_format} → {rep.output_format}</td>"
                f"<td>{rep.original_size:,}</td><td>{rep.final_size:,}</td><td>{rep.saved_bytes:,}</td>"
                f"<td>{rep.reduction_percent:.1f}%</td><td>{rep.estimated_quality:.1f}</td>"
                f"<td>{rep.ssim:.3f}</td><td>{status}</td></tr>"
            )
        else:
            n_errors += 1
            rows.append(f"<tr><td>{r.input_path}</td><td colspan='7'><span class='bad'>{r.error}</span></td><td>failed</td></tr>")

    avg_reduction = sum(reductions) / len(reductions) if reductions else 0.0
    return _HTML_TEMPLATE.format(
        n_files=len(results), total_saved=f"{total_saved:,}", avg_reduction=avg_reduction,
        n_errors=n_errors, rows="\n".join(rows),
    )
