"""CLI entry point: python -m nanopore run <path> [options]."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .config import PipelineConfig
from .mods import all_mods, resolve_mods
from .registry import detector_ids, normalize_config
from .fingerprint import describer_ids


def _parse_scalar(text: str):
    """Parse a --fp-param value into bool/int/float/str."""
    value = text.strip()
    low = value.lower()
    if low in ("true", "false"):
        return low == "true"
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="moltrace",
                                description="MOLTRACE — single-molecule nanopore .abf analysis pipeline")
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
                        "refined_anomaly,describe,plots,waveform_export,dataset_export,summary); "
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
    r.add_argument("--detector", choices=detector_ids(), default=None,
                   help="event detector: level (Clampfit semantics, default), burst "
                        "(dwell-envelope debounce), or plateau (hysteresis platform; keeps "
                        "partial recoveries inside one event)")
    r.add_argument("--describe", choices=describer_ids(), default=None,
                   help="enable event description (fingerprint segments) and pick the "
                        "describer; writes <name>_fingerprints.xlsx/.json")
    r.add_argument("--describers", default=None, metavar="ID[,ID…]",
                   help="run several describers in one pass: the first writes the "
                        "historical <name>_fingerprints.* files, each extra one writes "
                        "<name>_fingerprints_<id>.* (e.g. --describers dp_bic,classic)")
    r.add_argument("--fp-param", action="append", default=None, metavar="KEY=VALUE",
                   help="describer parameter override, repeatable "
                        "(e.g. --fp-param k_max=50 --fp-param tau_min_us=200)")
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

    rs = sub.add_parser(
        "research",
        help="experimental shape discovery (PELT/DTW/Fréchet/DBA; not validated)")
    rsub = rs.add_subparsers(dest="research_command", required=True)

    def add_research_common(sp, *, output_help: str, output_default: str) -> None:
        sp.add_argument("path", help=".abf file or directory")
        sp.add_argument("-o", "--output", default=output_default,
                        help=output_help)
        sp.add_argument("--config", default=None, help="JSON parameter file")
        sp.add_argument("--detector", choices=detector_ids(), default=None,
                        help="event detector used to build the corpus")
        sp.add_argument("--polarity", choices=("auto", "up", "down", "both"),
                        default="auto", help="event search direction")
        sp.add_argument("--level0", type=float, default=None)
        sp.add_argument("--level1", type=float, default=None)
        sp.add_argument("--limit", type=int, default=200,
                        help="maximum number of kept events in the corpus")

    fit = rsub.add_parser("fit", help="fit a shape vocabulary on a corpus")
    add_research_common(fit, output_help="model JSON path",
                        output_default="shape_vocab.json")
    fit.add_argument("--pen-mult", type=float, default=8.0)
    fit.add_argument("--smooth-ms", type=float, default=0.5)
    fit.add_argument("--min-frag-ms", type=float, default=0.5)
    fit.add_argument("--edge-gap-ms", type=float, default=0.5)
    fit.add_argument("--mode", choices=("R1", "R2"), default="R1")
    fit.add_argument("--alpha", type=float, default=1.0)
    fit.add_argument("--dist", choices=("dtw", "frechet", "euclid"),
                     default="dtw")
    fit.add_argument("--cap", type=int, default=1200)
    fit.add_argument("--thresh-frac", type=float, default=0.5)
    fit.add_argument("--min-support", type=int, default=5)
    fit.add_argument("--n-iter-dba", type=int, default=5)
    fit.add_argument("--nulls", action="store_true",
                     help="also report same-pipeline null AUC (N1/N2)")
    fit.add_argument("--leave-one-file", action="store_true",
                     help="also report held-out-file reproduction")
    fit.add_argument("--report", default=None,
                     help="write the null / leave-one-file report to this JSON")
    fit.add_argument("--seed", type=int, default=0)

    dec = rsub.add_parser("decode", help="decode events with a saved vocabulary")
    add_research_common(dec, output_help="output directory",
                        output_default="output_research")
    dec.add_argument("--model", required=True, help="model JSON path")
    dec.add_argument("--accept-frac", type=float, default=1.0,
                     help="acceptance threshold as a multiple of the cluster threshold")

    nls = rsub.add_parser("nulls", help="report null AUC for a saved vocabulary")
    add_research_common(nls, output_help="report JSON path",
                        output_default="shape_nulls.json")
    nls.add_argument("--model", required=True, help="model JSON path")
    nls.add_argument("--seed", type=int, default=0)

    return p


def _research_config(args) -> PipelineConfig:
    cfg = PipelineConfig.load(args.config) if args.config else PipelineConfig()
    if args.level0 is not None:
        cfg.level0 = args.level0
    if args.level1 is not None:
        cfg.level1 = args.level1
    if args.polarity != "auto":
        cfg.polarity = {"up": 1, "down": -1, "both": 0}[args.polarity]
    if args.detector is not None:
        cfg.detector = args.detector
        cfg.event_mode = "burst" if args.detector == "burst" else "level"
    cfg.enabled_mods = resolve_mods(tuple(cfg.enabled_mods))
    return normalize_config(cfg)


def _research_files(path: Path) -> list[Path]:
    if path.is_dir():
        return sorted(p for p in path.rglob("*.abf") if p.is_file())
    return [path] if path.is_file() else []


def _research_main(args) -> int:
    from .fingerprint import get_describer
    from .fingerprint.research import (ResearchDependencyError, ShapeModel,
                                       build_corpus, decode_corpus,
                                       fit_vocabulary, leave_one_file,
                                       missing_dependencies, null_report,
                                       write_decoded_by_source)

    missing = missing_dependencies()
    if missing:
        print("error: 实验性形状研究缺少依赖：" + ", ".join(missing)
              + '。请安装：pip install -e ".[research]"', file=sys.stderr)
        return 2

    path = Path(args.path)
    if not path.exists():
        print(f"error: path not found: {path}", file=sys.stderr)
        return 2
    files = _research_files(path)
    if not files:
        print(f"error: no .abf files under {path}", file=sys.stderr)
        return 2

    cfg = _research_config(args)
    print(f"research: {len(files)} file(s), limit {args.limit}, "
          f"detector {cfg.detector or cfg.event_mode}")
    try:
        corpus = build_corpus(
            files, cfg, limit=args.limit,
            progress=lambda i, n, name: print(f"  [{i}/{n}] {name}", flush=True))
        print(f"corpus: {corpus.n_events} kept events")
        if corpus.n_events == 0:
            print("error: corpus is empty", file=sys.stderr)
            return 1

        if args.research_command == "fit":
            params = {
                "pen_mult": args.pen_mult, "smooth_ms": args.smooth_ms,
                "min_frag_ms": args.min_frag_ms,
                "edge_gap_ms": args.edge_gap_ms, "mode": args.mode,
                "alpha": args.alpha, "dist": args.dist, "cap": args.cap,
                "thresh_frac": args.thresh_frac,
                "min_support": args.min_support,
                "n_iter_dba": args.n_iter_dba,
            }
            model = fit_vocabulary(corpus, params)
            out = model.save(args.output)
            print(f"vocabulary: M={len(model.centers)} threshold={model.threshold:.4g} "
                  f"support={model.support} -> {out}")
            report = {}
            if args.nulls:
                report["nulls"] = null_report(corpus, model,
                                              max_events=args.limit,
                                              seed=args.seed)
            if args.leave_one_file:
                report["leave_one_file"] = leave_one_file(
                    corpus, get_describer("shape_vocab"), params,
                    seed=args.seed, with_nulls=args.nulls)
            if report:
                rp = Path(args.report) if args.report else Path(args.output).with_suffix(".report.json")
                rp.parent.mkdir(parents=True, exist_ok=True)
                rp.write_text(json.dumps(report, ensure_ascii=False, indent=1,
                                         default=str), encoding="utf-8")
                print(f"report: {rp}")
            return 0

        if args.research_command == "decode":
            model = ShapeModel.load(args.model)
            descs = decode_corpus(corpus, model,
                                  {"accept_frac": args.accept_frac})
            written = write_decoded_by_source(corpus, descs, args.output)
            for item in written:
                print(f"decoded: {item['source']} -> {item['xlsx']}")
            return 0

        if args.research_command == "nulls":
            model = ShapeModel.load(args.model)
            report = null_report(corpus, model, max_events=args.limit,
                                 seed=args.seed)
            out = Path(args.output)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(report, ensure_ascii=False, indent=1,
                                      default=str), encoding="utf-8")
            print(f"null report -> {out}")
            return 0
    except ResearchDependencyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 — CLI should print, not traceback
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 2


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "research":
        return _research_main(args)

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
    if args.describe is not None:
        cfg.enabled_mods = resolve_mods(tuple(cfg.enabled_mods) + ("describe",))
        cfg.describer = args.describe
    if args.describers:
        ids = [s.strip() for s in args.describers.split(",") if s.strip()]
        unknown = [i for i in ids if i not in describer_ids()]
        if unknown:
            print(f"error: unknown describer id(s): {', '.join(unknown)}; "
                  f"available: {', '.join(describer_ids())}", file=sys.stderr)
            return 2
        cfg.enabled_mods = resolve_mods(tuple(cfg.enabled_mods) + ("describe",))
        cfg.describer = ids[0]
        cfg.describers = tuple(ids[1:])
    for item in args.fp_param or []:
        key, sep, value = item.partition("=")
        if not sep or not key.strip():
            print(f"error: --fp-param expects KEY=VALUE, got {item!r}", file=sys.stderr)
            return 2
        cfg.describe_params[key.strip()] = _parse_scalar(value)
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
    cfg = normalize_config(cfg)
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
