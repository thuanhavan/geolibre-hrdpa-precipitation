from __future__ import annotations

import argparse
import json
from dataclasses import fields
from datetime import date
from pathlib import Path

from .core import (
    Audit,
    COLLECTION,
    CRS,
    PROJECT,
    ROI,
    SCALE_METRES,
    audit_collection,
    build_cube,
    default_start,
    download_available,
    parse_date,
    write_audit,
)


def load_audit(path: Path) -> Audit:
    raw = json.loads(path.read_text(encoding="utf-8"))
    allowed = {field.name for field in fields(Audit)}
    return Audit(**{key: value for key, value in raw.items() if key in allowed})


def parser() -> argparse.ArgumentParser:
    today = date.today()
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--start", default=default_start(today).isoformat(), help="inclusive YYYY-MM-DD (default: May 1 this year)")
    common.add_argument("--end", default=today.isoformat(), help="inclusive YYYY-MM-DD (default: today)")
    common.add_argument("--project", default=PROJECT)
    common.add_argument("--collection", default=COLLECTION)
    common.add_argument("--reports", type=Path, default=Path("reports"))

    root = argparse.ArgumentParser(description="HRDPA-to-GeoZarr pipeline")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("audit", parents=[common], help="check GEE coverage and report missing dates")
    download = commands.add_parser("download", parents=[common], help="audit and download available clipped daily rasters")
    download.add_argument("--daily-dir", type=Path, default=Path("data/daily"))
    download.add_argument("--roi", default=ROI)
    download.add_argument("--band")
    download.add_argument("--crs", default=CRS)
    download.add_argument("--scale", type=int, default=SCALE_METRES)
    download.add_argument("--overwrite", action="store_true")
    build = commands.add_parser("build", help="stack downloaded rasters into one Zarr v2 cube")
    build.add_argument("--daily-dir", type=Path, default=Path("data/daily"))
    build.add_argument("--output", type=Path, default=Path("output/hrdpa_prairies_daily.zarr"))
    build.add_argument("--audit", type=Path, default=Path("reports/date_audit.json"))
    run = commands.add_parser("run", parents=[common], help="audit, download, and build")
    run.add_argument("--daily-dir", type=Path, default=Path("data/daily"))
    run.add_argument("--output", type=Path, default=Path("output/hrdpa_prairies_daily.zarr"))
    run.add_argument("--roi", default=ROI)
    run.add_argument("--band")
    run.add_argument("--crs", default=CRS)
    run.add_argument("--scale", type=int, default=SCALE_METRES)
    run.add_argument("--overwrite", action="store_true")
    return root


def do_audit(args) -> Audit:
    result = audit_collection(parse_date(args.start), parse_date(args.end), args.collection, args.project)
    write_audit(result, args.reports)
    print(f"GEE images: {result.image_count}; available days: {len(result.available_dates)}; missing days: {len(result.missing_dates)}")
    if result.missing_dates:
        print("Missing: " + ", ".join(result.missing_dates))
    return result


def main() -> None:
    args = parser().parse_args()
    if args.command == "audit":
        do_audit(args)
    elif args.command == "download":
        result = do_audit(args)
        selected = download_available(result, args.daily_dir, args.band, args.collection, args.roi, args.project, args.crs, args.scale, args.overwrite)
        print(f"Daily rasters ready in {args.daily_dir} (source band: {selected})")
    elif args.command == "build":
        result = load_audit(args.audit) if args.audit.exists() else None
        count = build_cube(args.daily_dir, args.output, result)
        print(f"Wrote {count} daily slices to {args.output}")
    elif args.command == "run":
        result = do_audit(args)
        selected = download_available(result, args.daily_dir, args.band, args.collection, args.roi, args.project, args.crs, args.scale, args.overwrite)
        count = build_cube(args.daily_dir, args.output, result)
        print(f"Wrote {count} daily slices to {args.output} (source band: {selected})")


if __name__ == "__main__":
    main()

