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
                        "refined_anomaly,plots,waveform_export,dataset_export,summary); "
                        "dependencies are added automatically. Overrides the config file's "
                        "enabled_mods.")
    r.add_argument("--minimal", action="store_true", help="base pipeline only, no mods")
    r.add_argument("--all", action="store_true", help="enable every mod")
    r.add_argument("--level0", type=float, default=None, help="manual baseline (pA), skips auto estimation")
    r.add_argument("--level1", type=float, default=None, help="manual event level (pA)")
    r.add_argument("--polarity", choices=("auto", "up", "down", "both"), default="auto",
                   help="event search direction (default auto from the level histogram); "
                        "'both' enables multi-level detection on either side of the baseline "
                        "(needed for peptides like ARNKRS whose blockades go both ways)")
    r.add_argument("--detector", choices=("level", "burst", "plateau"), default=None,
                   help="event detector: level (Clampfit semantics, default), burst "
                        "(dwell-envelope debounce), or plateau (hysteresis platform; keeps "
                        "partial recoveries inside one event)")
    r.add_argument("--event-mode", choices=("level", "burst"), default=None,
                   help="legacy alias for --detector (kept for older configs/scripts)")
    r.add_argument("--burst-enter-frac", type=float, default=None,
                   help="burst: |I-I0| > this x level-step enters a blockade (default 0.30)")
    r.add_argument("--burst-exit-frac", type=float, default=None,
                   help="burst: amplitude read from samples beyond this x step (default 0.20)")
    r.add_argument("--burst-min-gap-ms", type=float, default=None,
                   help="burst: returns to open shorter than this do NOT split (default 30 ms)")
    r.add_argument("--burst-min-block-ms", type=float, default=None,
                   help="burst: blocked fragments shorter than this are dropped (default 2 ms)")
    r.add_argument("--burst-open-cover", type=float, default=None,
                   help="burst: a gap splits only when at least this fraction of it lies "
                        "within +/-enter-frac of the open level (default 0.75)")
    r.add_argument("--burst-merge-max-ms", type=float, default=None,
                   help="burst: only merge non-open gaps up to this long (default 200 ms; "
                        "0 disables merging)")
    r.add_argument("--burst-cross-baseline", action="store_true",
                   help="burst: departures on EITHER side of the open pore count as one "
                        "event (multi-level / baseline-crossing signals)")
    r.add_argument("--burst-min-occupied-frac", type=float, default=None,
                   help="burst: reject events whose body is blocked for less than this "
                        "fraction of its dwell (default 0.30)")
    r.add_argument("--burst-min-depth-frac", type=float, default=None,
                   help="burst: ...unless the body median is deflected by this x step "
                        "(default 0.15; keeps shallow sustained states)")
    r.add_argument("--plateau-direction", choices=("auto", "down", "up", "both"), default=None,
                   help="plateau: blockade direction; auto follows --polarity (default auto)")
    r.add_argument("--plateau-enter-depth", type=float, default=None,
                   help="plateau: a run must reach this depth (pA) to be an event (default 60)")
    r.add_argument("--plateau-exit-depth", type=float, default=None,
                   help="plateau: event boundary sits at this distance from the open pore "
                        "(pA; default 15; smaller keeps partial recoveries inside an event)")
    r.add_argument("--plateau-min-open-ms", type=float, default=None,
                   help="plateau: returns to the open pore shorter than this do not split "
                        "an event (default 1 ms)")
    r.add_argument("--keep-voltage", action="store_true",
                   help="plateau: do NOT mask protocol-voltage segments")
    r.add_argument("--keep-pulse-cleared", action="store_true",
                   help="plateau: keep events terminated by a voltage pulse")
    r.add_argument("--keep-rupture", action="store_true",
                   help="plateau: keep membrane-rupture / pore-collapse pseudo-events")
    r.add_argument("--plateau-artifact-abs", type=float, default=None,
                   help="plateau: mask samples with |I| above this (pA; 0 disables; default 1000)")
    r.add_argument("--plateau-artifact-diff", type=float, default=None,
                   help="plateau: mask samples whose |dI| exceeds this (pA; 0 disables; default 500)")
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
    if args.event_mode is not None:
        cfg.event_mode = args.event_mode
        if not cfg.detector:
            cfg.detector = args.event_mode
    if args.detector is not None:
        cfg.detector = args.detector
        cfg.event_mode = "burst" if args.detector == "burst" else "level"
    for field, value in (("burst_enter_frac", args.burst_enter_frac),
                         ("burst_exit_frac", args.burst_exit_frac),
                         ("burst_min_gap_ms", args.burst_min_gap_ms),
                         ("burst_min_block_ms", args.burst_min_block_ms),
                         ("burst_open_cover", args.burst_open_cover),
                         ("burst_merge_max_ms", args.burst_merge_max_ms),
                         ("burst_min_occupied_frac", args.burst_min_occupied_frac),
                         ("burst_min_depth_frac", args.burst_min_depth_frac),
                         ("plateau_direction", args.plateau_direction),
                         ("plateau_enter_depth_pA", args.plateau_enter_depth),
                         ("plateau_exit_depth_pA", args.plateau_exit_depth),
                         ("plateau_min_open_ms", args.plateau_min_open_ms),
                         ("plateau_artifact_abs_pA", args.plateau_artifact_abs),
                         ("plateau_artifact_diff_pA", args.plateau_artifact_diff)):
        if value is not None:
            setattr(cfg, field, value)
    if args.burst_cross_baseline:
        cfg.burst_cross_baseline = True
    if args.keep_voltage:
        cfg.plateau_exclude_voltage = False
    if args.keep_pulse_cleared:
        cfg.plateau_exclude_pulse_cleared = False
    if args.keep_rupture:
        cfg.plateau_exclude_rupture = False
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
