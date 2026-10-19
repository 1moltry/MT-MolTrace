"""CLI entry point: python -m nanopore run <path> [options]."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .config import PipelineConfig
from .mods import all_mods, resolve_mods


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="nanopore", description="Automated nanopore .abf analysis pipeline")
    p.add_argument("--version", action="version", version=f"nanopore {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("run", help="batch process a file or directory of .abf files")
    r.add_argument("path", help=".abf file or directory containing .abf files")
    r.add_argument("-o", "--output", default="output", help="output directory (default: ./output)")
    r.add_argument("--config", default=None, help="JSON parameter file (see config.PipelineConfig)")
    r.add_argument("--label", default="", help="Label column override for the feature table")
    r.add_argument("--no-anomaly", action="store_true",
                   help="drop the anomaly mods from the enabled set (alias for --mods minus anomaly)")
    r.add_argument("--mods", default=None,
                   help="comma-separated mod ids to enable (lowpass,dynamic_i0,anomaly,"
                        "refined_anomaly,plots,dataset_export,summary); dependencies are added "
                        "automatically. Overrides the config file's enabled_mods.")
    r.add_argument("--minimal", action="store_true", help="base pipeline only, no mods")
    r.add_argument("--all", action="store_true", help="enable every mod")
    r.add_argument("--level0", type=float, default=None, help="manual baseline (pA), skips auto estimation")
    r.add_argument("--level1", type=float, default=None, help="manual event level (pA)")
    r.add_argument("--polarity", choices=("auto", "up", "down", "both"), default="auto",
                   help="event search direction (default auto from the level histogram); "
                        "'both' enables multi-level detection on either side of the baseline "
                        "(needed for peptides like ARNKRS whose blockades go both ways)")
    r.add_argument("--save-config", default=None, help="write the effective config to this JSON path and exit")

    g = sub.add_parser("gui", help="launch the interactive desktop GUI")
    g.add_argument("path", nargs="?", default=None, help=".abf file to open on launch")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "gui":
        from .gui.__main__ import main as gui_main

        gui_argv = [args.path] if args.path else []
        return gui_main(gui_argv)

    cfg = PipelineConfig.load(args.config) if args.config else PipelineConfig()
    if args.label:
        cfg.label = args.label
    # module selection: explicit flags override the config file's enabled_mods
    if args.all:
        cfg.enabled_mods = all_mods()
    elif args.minimal:
        cfg.enabled_mods = ()
    if args.mods is not None:
        cfg.enabled_mods = resolve_mods([s.strip() for s in args.mods.split(",") if s.strip()])
    if args.no_anomaly:
        cfg.enabled_mods = tuple(m for m in resolve_mods(cfg.enabled_mods)
                                 if m not in ("anomaly", "refined_anomaly"))
    if args.level0 is not None:
        cfg.level0 = args.level0
    if args.level1 is not None:
        cfg.level1 = args.level1
    if args.polarity != "auto":
        cfg.polarity = {"up": 1, "down": -1, "both": 0}[args.polarity]
    if args.save_config:
        cfg.save(args.save_config)
        print(f"config saved: {args.save_config}")
        return 0

    path = Path(args.path)
    if not path.exists():
        print(f"error: path not found: {path}", file=sys.stderr)
        return 2

    files = sorted(path.glob("*.abf")) if path.is_dir() else [path]
    files = [f for f in files if f.is_file()]
    if not files:
        print(f"error: no .abf files under {path}", file=sys.stderr)
        return 2

    out = Path(args.output)
    print(f"nanopore {__version__}: {len(files)} file(s) -> {out}")

    from .pipeline import run_batch

    reports = run_batch(files, out, cfg)
    ok = sum(1 for r in reports if not r.error)
    tail = f", summary at {out / 'summary.xlsx'}" if "summary" in resolve_mods(cfg.enabled_mods) else ""
    print(f"done: {ok}/{len(reports)} files processed{tail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
