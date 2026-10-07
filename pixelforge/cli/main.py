"""
PixelForge - Command Line Interface
=====================================

Headless automation surface, sharing the exact same core engine as the GUI
(see pipeline/pipeline.py). Every command supports --json for CI/CD-friendly
machine-readable output.

Commands
--------
  pixelforge compress <file> [options]        Compress a single image
  pixelforge auto <file> [--mode fast|balanced|deep]
  pixelforge batch <folder> [options]         Batch-process a whole folder
  pixelforge analyze <file>                   Print the Image Analysis Engine's features
  pixelforge benchmark <file>                 Run the Auto Compression Benchmark Engine and show all candidates
  pixelforge convert <file> --to <format>     Explicit format conversion
  pixelforge target <file> --size 500KB       Target-size compression
  pixelforge library-scan <folder>            Smart Library Mode
  pixelforge formats                          Format Explorer (codec availability)
  pixelforge report <job_id>                  Print a stored job's report from the database
  pixelforge history                          Show recent compression history
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict

from analysis import analyze_image
from compression import AutoMode
from database import Database
from imgcodecs import available_codecs, safe_open
from optimizer import Goal, list_presets
from pipeline import (
    process_single, PipelineOptions, BatchQueue, scan_folder, summarize,
    report_to_json, batch_to_json, batch_to_csv, batch_to_html, configure_logging,
)


def _parse_size(text: str) -> int:
    text = text.strip().upper()
    mult = 1
    if text.endswith("KB"):
        mult, text = 1024, text[:-2]
    elif text.endswith("MB"):
        mult, text = 1024 * 1024, text[:-2]
    elif text.endswith("B"):
        text = text[:-1]
    return int(float(text) * mult)


def _print(data, as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, default=str))
    else:
        if isinstance(data, dict):
            for k, v in data.items():
                print(f"{k}: {v}")
        else:
            print(data)


def cmd_compress(args) -> int:
    opt = PipelineOptions(
        goal=Goal(args.goal), auto_mode=AutoMode(args.mode),
        output_dir=args.output_dir, output_path=args.output,
        min_ssim=args.min_ssim, metadata_policy=args.metadata,
        privacy_mode=args.privacy,
    )
    report = process_single(args.file, opt)
    _print(asdict(report), args.json)
    return 0


def cmd_auto(args) -> int:
    opt = PipelineOptions(goal=Goal.BALANCED, auto_mode=AutoMode(args.mode), output_dir=args.output_dir)
    report = process_single(args.file, opt)
    _print(asdict(report), args.json)
    return 0


def cmd_batch(args) -> int:
    db = Database(args.db)
    opt = PipelineOptions(goal=Goal(args.goal), auto_mode=AutoMode(args.mode), output_dir=args.output_dir)
    paths = []
    for root, _dirs, files in os.walk(args.folder):
        for f in files:
            if os.path.splitext(f)[1].lower() in (".jpg", ".jpeg", ".png", ".webp", ".avif",
                                                     ".tif", ".tiff", ".bmp", ".gif", ".ppm"):
                paths.append(os.path.join(root, f))
        if not args.recursive:
            break
    q = BatchQueue(db, opt, max_workers=args.workers)
    job_id = q.add_files(paths)
    results = q.run()

    if args.report_format == "csv":
        out = batch_to_csv(results)
    elif args.report_format == "html":
        out = batch_to_html(results)
    else:
        out = batch_to_json(results)

    if args.report_out:
        with open(args.report_out, "w", encoding="utf-8") as fh:
            fh.write(out)
        print(f"Report written to {args.report_out}")
    else:
        print(out)
    print(f"Job #{job_id}: {len(results)} files processed.", file=sys.stderr)
    return 0


def cmd_analyze(args) -> int:
    img = safe_open(args.file)
    features = analyze_image(args.file, img)
    _print(asdict(features), args.json)
    return 0


def cmd_benchmark(args) -> int:
    from compression import run_benchmark, pick_best
    from optimizer import decide

    img = safe_open(args.file)
    features = analyze_image(args.file, img)
    decision = decide(features, Goal(args.goal))
    entries = run_benchmark(args.file, img, decision, mode=AutoMode(args.mode))
    data = [
        {"format": e.format, "params": e.params, "size_bytes": e.size_bytes,
         "encode_time_s": e.encode_time_s, "ssim": e.metrics.ssim, "psnr": e.metrics.psnr,
         "estimated_quality": e.metrics.estimated_quality, "score": e.score}
        for e in entries
    ]
    best = pick_best(entries, Goal(args.goal))
    _print({"reasons": decision.reasons, "candidates": data,
            "best": best.format if best else None}, args.json)
    return 0


def cmd_convert(args) -> int:
    from imgcodecs import ENCODERS
    img = safe_open(args.file)
    fmt = args.to.upper()
    if fmt not in ENCODERS:
        print(f"Unsupported/unknown format: {fmt}", file=sys.stderr)
        return 1
    out_path = args.output or (os.path.splitext(args.file)[0] + f".{fmt.lower()}")
    params = json.loads(args.params) if args.params else {}
    result = ENCODERS[fmt](img, out_path, **params)
    _print(asdict(result), args.json)
    return 0


def cmd_target(args) -> int:
    from compression.target_size import compress_to_target_size
    img = safe_open(args.file)
    fmt = args.format.upper() if args.format else "JPEG"
    target_bytes = _parse_size(args.size)
    result = compress_to_target_size(img, fmt, target_bytes, out_path=args.output)
    _print(asdict(result), args.json)
    return 0


def cmd_library_scan(args) -> int:
    entries = scan_folder(args.folder, recursive=not args.no_recursive, goal=Goal(args.goal))
    summary = summarize(entries)
    _print({"summary": summary, "files": [asdict(e) for e in entries]}, args.json)
    return 0


def cmd_formats(args) -> int:
    _print(available_codecs(), args.json)
    return 0


def cmd_presets(args) -> int:
    _print(list_presets(), args.json)
    return 0


def cmd_history(args) -> int:
    db = Database(args.db)
    rows = [dict(r) for r in db.get_history(limit=args.limit)]
    _print(rows, args.json)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pixelforge", description="Universal Intelligent Image Compression Studio")
    p.add_argument("--json", action="store_true", help="Machine-readable JSON output (for CI/CD)")
    p.add_argument("--db", default="pixelforge.db", help="Path to the PixelForge SQLite database")
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("compress", help="Compress a single image with Automatic Mode")
    c.add_argument("file")
    c.add_argument("--goal", default="balanced", choices=[g.value for g in Goal])
    c.add_argument("--mode", default="balanced", choices=[m.value for m in AutoMode])
    c.add_argument("--output", "-o", default=None)
    c.add_argument("--output-dir", default=None)
    c.add_argument("--min-ssim", type=float, default=0.90)
    c.add_argument("--metadata", default="keep_selected", choices=["keep_all", "keep_selected", "remove_all"])
    c.add_argument("--privacy", action="store_true")
    c.set_defaults(func=cmd_compress)

    a = sub.add_parser("auto", help="Fully automatic compression (shortcut for compress --goal balanced)")
    a.add_argument("file")
    a.add_argument("--mode", default="balanced", choices=[m.value for m in AutoMode])
    a.add_argument("--output-dir", default=None)
    a.set_defaults(func=cmd_auto)

    b = sub.add_parser("batch", help="Batch-process every image in a folder")
    b.add_argument("folder")
    b.add_argument("--goal", default="balanced", choices=[g.value for g in Goal])
    b.add_argument("--mode", default="fast", choices=[m.value for m in AutoMode])
    b.add_argument("--output-dir", default=None)
    b.add_argument("--recursive", action="store_true")
    b.add_argument("--workers", type=int, default=None)
    b.add_argument("--report-format", default="json", choices=["json", "csv", "html"])
    b.add_argument("--report-out", default=None)
    b.set_defaults(func=cmd_batch)

    an = sub.add_parser("analyze", help="Run the Image Analysis Engine and print the extracted features")
    an.add_argument("file")
    an.set_defaults(func=cmd_analyze)

    bm = sub.add_parser("benchmark", help="Run the Auto Compression Benchmark Engine")
    bm.add_argument("file")
    bm.add_argument("--goal", default="balanced", choices=[g.value for g in Goal])
    bm.add_argument("--mode", default="balanced", choices=[m.value for m in AutoMode])
    bm.set_defaults(func=cmd_benchmark)

    cv = sub.add_parser("convert", help="Explicit format conversion (Expert Mode)")
    cv.add_argument("file")
    cv.add_argument("--to", required=True, help="Target format, e.g. AVIF, WEBP, JPEG, PNG")
    cv.add_argument("--output", "-o", default=None)
    cv.add_argument("--params", default=None, help="JSON dict of encoder parameters")
    cv.add_argument("--auto", action="store_true", help="(reserved) let the decision engine pick parameters")
    cv.set_defaults(func=cmd_convert)

    tg = sub.add_parser("target", help="Compress to a specific target file size")
    tg.add_argument("file")
    tg.add_argument("--size", required=True, help="e.g. 500KB, 2MB, 200000B")
    tg.add_argument("--format", default=None, help="JPEG | WEBP | AVIF (defaults to JPEG)")
    tg.add_argument("--output", "-o", default=None)
    tg.set_defaults(func=cmd_target)

    ls = sub.add_parser("library-scan", help="Smart Library Mode: estimate savings across a folder")
    ls.add_argument("folder")
    ls.add_argument("--goal", default="balanced", choices=[g.value for g in Goal])
    ls.add_argument("--no-recursive", action="store_true")
    ls.set_defaults(func=cmd_library_scan)

    fe = sub.add_parser("formats", help="Format Explorer: show which codecs are available on this system")
    fe.set_defaults(func=cmd_formats)

    pr = sub.add_parser("presets", help="List built-in presets")
    pr.set_defaults(func=cmd_presets)

    hi = sub.add_parser("history", help="Show recent compression history from the database")
    hi.add_argument("--limit", type=int, default=50)
    hi.set_defaults(func=cmd_history)

    rp = sub.add_parser("report", help="(alias) print history - kept for the spec's `pixelforge report <job-id>` form")
    rp.add_argument("job_id")
    rp.set_defaults(func=lambda args: cmd_history(args))

    return p


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:  # noqa: BLE001 - CLI top-level error boundary
        if args.json:
            print(json.dumps({"error": str(exc)}))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
