"""End-to-end batch pipeline: read -> analyze (base + enabled mods) -> outputs.

The per-file analysis itself lives in :func:`nanopore.analyze.analyze`, shared
with the GUI worker. Here we only orchestrate files, write the per-file events
table, and (when their mods are enabled) the figures, the combined dataset and
the batch summary.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from .analysis import (build_combined_dataset, plot_hist, plot_overview,
                       plot_scatter, write_combined_dataset, write_event_waveforms,
                       write_events_xlsx, write_fingerprints, write_summary)
from .analyze import analyze
from .anomaly import AnomalyResult
from .config import PipelineConfig
from .io import read_abf
from .mods import resolve_mods


@dataclass
class FileReport:
    file: str
    label: str
    duration_s: float
    n_events_raw: int
    n_events: int
    n_brief: int
    valid_pct: float | None
    level0: float
    levels: list[float] = field(default_factory=list)
    polarity: int = 0
    noise_sigma: float = 0.0
    anomalies: dict = field(default_factory=dict)
    removed: dict = field(default_factory=dict)
    error: str = ""
    elapsed_s: float = 0.0
    detector: str = ""
    anomaly_enabled: bool = False
    n_detector_rejected: int = 0


def process_file(abf_path: Path, out_dir: Path, cfg: PipelineConfig) -> tuple[pd.DataFrame, FileReport]:
    t0 = time.perf_counter()
    label = cfg.label or abf_path.stem
    rec = read_abf(abf_path)
    res = analyze(rec, cfg)
    mods = set(resolve_mods(cfg.enabled_mods))

    stem = abf_path.stem
    write_events_xlsx(res.df, res.anom.regions if res.anom else [],
                      out_dir / f"{stem}_events.xlsx", excluded=res.df_excluded)

    if "describe" in mods and res.descs is not None:
        write_fingerprints(res.descs, out_dir, stem, fs=rec.sample_rate_hz,
                           source=abf_path.name)

    if "waveform_export" in mods:
        write_event_waveforms(
            res.df, rec.current, rec.sample_rate_hz,
            out_dir / f"{stem}_events.mat",
            label=label, source_file=abf_path.name, units=rec.units,
        )

    if "plots" in mods:
        anom = res.anom if res.anom is not None else AnomalyResult(
            [], np.ones(1, dtype=bool), np.array([]), 0.1, res.lv.level0)
        plot_overview(
            rec.current, rec.sample_rate_hz,
            res.df["t1"].to_numpy() if len(res.df) else np.array([]),
            res.df["t2"].to_numpy() if len(res.df) else np.array([]),
            anom, res.lv, out_dir / f"{stem}_overview.png", label=label,
        )
        plot_scatter(res.df, out_dir / f"{stem}_scatter.png", label=label)
        plot_hist(res.df, out_dir / f"{stem}_hist.png", label=label)

    n_anom: dict[str, int] = {}
    if res.anom is not None:
        for r in res.anom.regions:
            n_anom[r.kind] = n_anom.get(r.kind, 0) + 1

    removed: dict[str, int] = {}
    if res.df_excluded is not None and len(res.df_excluded):
        for reason in res.df_excluded["drop_reason"]:
            for part in re.split(r"[,|]", str(reason)):
                if part:
                    removed[part] = removed.get(part, 0) + 1

    report = FileReport(
        file=abf_path.name,
        label=label,
        duration_s=rec.duration_s,
        n_events_raw=len(res.det.events) + len(res.det.rejected),
        n_events=len(res.df),
        n_brief=sum(1 for e in res.det.events if e.state == "B"),
        valid_pct=(float(res.anom.valid.mean() * 100)
                   if res.anom is not None else None),
        level0=res.lv.level0,
        levels=[round(v, 1) for v in res.lv.levels],
        polarity=res.lv.polarity,
        noise_sigma=res.lv.noise_sigma,
        anomalies=n_anom,
        removed=removed,
        elapsed_s=time.perf_counter() - t0,
        detector=res.detector_id,
        anomaly_enabled=res.anomaly_enabled,
        n_detector_rejected=res.detector_rejected,
    )
    return res.df, report


def run_batch(files: list[Path], out_dir: Path, cfg: PipelineConfig,
              progress=None) -> list[FileReport]:
    """Process ``files`` into ``out_dir``, continuing past a bad file.

    ``progress`` (optional) is called as ``progress(i, total, file_name, report)``
    before each file finishes, so a GUI can show a live counter.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    mods = set(resolve_mods(cfg.enabled_mods))
    reports: list[FileReport] = []
    dataset: list[tuple[str, pd.DataFrame]] = []   # (source_file, kept events)
    for i, f in enumerate(files, start=1):
        try:
            df, rep = process_file(f, out_dir, cfg)
            dataset.append((f.name, df))
        except Exception as exc:  # keep batch going on a bad file
            rep = FileReport(file=f.name, label=cfg.label or f.stem, duration_s=0.0,
                             n_events_raw=0, n_events=0, n_brief=0, valid_pct=0.0,
                             level0=0.0, error=f"{type(exc).__name__}: {exc}")
        reports.append(rep)
        if rep.error:
            status = f"err {rep.error}"
        else:
            valid = (f"{rep.valid_pct:.0f}%" if rep.valid_pct is not None
                     else "n/a (anomaly off)")
            status = (f"{rep.n_events} events (of {rep.n_events_raw} candidates), "
                      f"valid {valid}")
        print(f"  {f.name}: {status} [{rep.elapsed_s:.1f}s]")
        if progress is not None:
            progress(i, len(files), f.name, rep)

    rows = []
    for rep in reports:
        rows.append({
            "file": rep.file, "label": rep.label, "duration_s": round(rep.duration_s, 1),
            "events": rep.n_events, "events_raw": rep.n_events_raw, "brief": rep.n_brief,
            "valid_pct": (None if rep.valid_pct is None else round(rep.valid_pct, 1)),
            "detector": rep.detector,
            "anomaly_enabled": rep.anomaly_enabled,
            "detector_rejected": rep.n_detector_rejected,
            "level0_pA": round(rep.level0, 1), "n_levels": len(rep.levels),
            "polarity": rep.polarity, "noise_sigma_pA": round(rep.noise_sigma, 2),
            "anomalies": "; ".join(f"{k}x{v}" for k, v in rep.anomalies.items()),
            "removed": "; ".join(f"{k}x{v}" for k, v in rep.removed.items()),
            "error": rep.error, "elapsed_s": round(rep.elapsed_s, 1),
        })
    if "dataset_export" in mods:
        write_combined_dataset(build_combined_dataset(dataset), out_dir / "dataset_all.csv")
    if "summary" in mods:
        write_summary(rows, out_dir / "summary.xlsx")
    return reports
