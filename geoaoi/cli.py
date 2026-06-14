"""GEOAOI command-line interface (argparse, stdlib-only)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from . import TOOL_NAME, TOOL_VERSION
from .core import (
    Geofence,
    compute_bbox,
    diff_events,
    geofence_check,
    parse_points_csv,
    parse_polygon,
)


def _read(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def _emit(obj, fmt: str, columns: Sequence[str]) -> None:
    if fmt == "json":
        print(json.dumps(obj, indent=2, sort_keys=True))
        return
    rows = obj if isinstance(obj, list) else [obj]
    if not rows:
        print("(no rows)")
        return
    widths = {c: len(c) for c in columns}
    for r in rows:
        for c in columns:
            widths[c] = max(widths[c], len(_cell(r.get(c))))
    header = "  ".join(c.ljust(widths[c]) for c in columns)
    print(header)
    print("  ".join("-" * widths[c] for c in columns))
    for r in rows:
        print("  ".join(_cell(r.get(c)).ljust(widths[c]) for c in columns))


def _cell(v) -> str:
    if v is None:
        return "-"
    if isinstance(v, bool):
        return "yes" if v else "no"
    return str(v)


def _cmd_bbox(args) -> int:
    pts = parse_points_csv(_read(args.input))
    box = compute_bbox(pts)
    _emit(box.to_dict(), args.format, [
        "min_lat", "min_lon", "max_lat", "max_lon",
        "center_lat", "center_lon", "width_m", "height_m", "count",
    ])
    return 0


def _cmd_geofence(args) -> int:
    pts = parse_points_csv(_read(args.input))
    if args.polygon:
        fence = Geofence(name=args.name, polygon=parse_polygon(args.polygon))
    elif args.center is not None and args.radius is not None:
        center_parts = args.center.split(",")
        if len(center_parts) != 2:
            print(
                f"error: --center must be 'lat,lon', got {args.center!r}",
                file=sys.stderr,
            )
            return 2
        try:
            clat, clon = float(center_parts[0]), float(center_parts[1])
        except ValueError:
            print(
                f"error: --center has non-numeric coordinate: {args.center!r}",
                file=sys.stderr,
            )
            return 2
        if args.radius <= 0:
            print(
                f"error: --radius must be a positive number, got {args.radius}",
                file=sys.stderr,
            )
            return 2
        fence = Geofence(name=args.name, center=(clat, clon), radius_m=args.radius)
    else:
        print("error: provide --polygon OR (--center and --radius)", file=sys.stderr)
        return 2
    results = geofence_check(pts, fence)
    cols = ["ident", "ts", "lat", "lon", "inside"]
    if any("distance_m" in r for r in results):
        cols.append("distance_m")
    _emit(results, args.format, cols)
    # Failure semantics: non-zero if any point is OUTSIDE a required AOI.
    breaches = sum(1 for r in results if not r["inside"])
    if args.require_inside and breaches:
        print(f"# {breaches} point(s) outside geofence {fence.name!r}", file=sys.stderr)
        return 1
    return 0


def _cmd_diff(args) -> int:
    if args.threshold < 0:
        print(
            f"error: --threshold must be >= 0, got {args.threshold}",
            file=sys.stderr,
        )
        return 2
    before = parse_points_csv(_read(args.before))
    after = parse_points_csv(_read(args.after))
    events = diff_events(before, after, move_threshold_m=args.threshold)
    _emit(events, args.format, ["ident", "event", "lat", "lon", "moved_m"])
    changed = [e for e in events if e["event"] in ("enter", "exit", "move")]
    if args.fail_on_change and changed:
        print(f"# {len(changed)} change event(s) detected", file=sys.stderr)
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=TOOL_NAME,
        description="Area-of-interest GEOINT helper: bbox, geofence, change diffs.",
    )
    p.add_argument("--version", action="version", version=f"{TOOL_NAME} {TOOL_VERSION}")
    p.add_argument("--format", choices=("table", "json"), default="table")
    sub = p.add_subparsers(dest="command", required=True)

    b = sub.add_parser("bbox", help="compute bounding box of a coordinate log")
    b.add_argument("input", help="CSV path or - for stdin")
    b.set_defaults(func=_cmd_bbox)

    g = sub.add_parser("geofence", help="check point membership in a geofence")
    g.add_argument("input", help="CSV path or - for stdin")
    g.add_argument("--name", default="aoi")
    g.add_argument("--polygon", help="'lat,lon;lat,lon;...' (>=3 vertices)")
    g.add_argument("--center", help="'lat,lon' for a circular fence")
    g.add_argument("--radius", type=float, help="radius in meters (with --center)")
    g.add_argument("--require-inside", action="store_true",
                   help="exit non-zero if any point falls outside")
    g.set_defaults(func=_cmd_geofence)

    d = sub.add_parser("diff", help="diff two coordinate logs into change events")
    d.add_argument("before", help="earlier CSV path or -")
    d.add_argument("after", help="later CSV path or -")
    d.add_argument("--threshold", type=float, default=50.0,
                   help="meters of displacement to count as a move (default 50)")
    d.add_argument("--fail-on-change", action="store_true",
                   help="exit non-zero if any enter/exit/move event occurs")
    d.set_defaults(func=_cmd_diff)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, FileNotFoundError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
