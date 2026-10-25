"""Detector diagnostics: plateau rejections and masks are traceable."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from nanopore.analyze import analyze
from nanopore.config import PipelineConfig
from nanopore.detect_plateau import detect_plateau
from nanopore.io import AbfRecording

FS = 25_000.0
OPEN = 370.0


def _trace(events, duration_s=1.0, noise=1.0, seed=0):
    n = int(round(duration_s * FS))
    x = np.full(n, OPEN, dtype=float)
    for a, b, level in events:
        x[int(round(a * FS)):int(round(b * FS))] = level
    return x + np.random.default_rng(seed).normal(0.0, noise, n)


def test_plateau_rupture_rejection_is_reported():
    x = _trace([(0.30, 0.40, 0.0)])
    res = detect_plateau(x, FS, OPEN, direction="down", enter_depth_pA=60.0,
                         exit_depth_pA=15.0, exclude_rupture=True)
    assert res.events == []
    assert [r.code for r in res.rejected] == ["plateau:rupture"]
    assert res.diagnostics["rupture"] == 1


def test_plateau_pulse_rejection_and_mask_are_reported():
    x = _trace([(0.30, 0.40, 250.0)])
    voltage = np.zeros_like(x)
    voltage[int(0.40 * FS):int(0.50 * FS)] = 100.0
    res = detect_plateau(
        x, FS, OPEN, voltage=voltage, direction="down",
        enter_depth_pA=60.0, exit_depth_pA=15.0,
        exclude_pulse_cleared=True, pulse_tol_ms=50.0,
    )
    assert res.events == []
    assert "plateau:pulse_cleared" in [r.code for r in res.rejected]
    assert res.masked_intervals
    assert res.diagnostics["masked_samples"] > 0


def test_plateau_rejections_enter_excluded_table_without_anomaly():
    x = _trace([(0.20, 0.50, 250.0), (0.70, 0.80, 0.0)])
    rec = AbfRecording(path=Path("plateau_reject.abf"), current=x,
                       sample_rate_hz=FS, units="pA", n_channels=1, sweep_count=1)
    cfg = PipelineConfig(detector="plateau", level0=OPEN, level1=250.0,
                         polarity=-1, plateau_direction="down",
                         min_toff_ms=0.0, enabled_mods=())
    res = analyze(rec, cfg)

    assert res.anomaly_enabled is False
    assert res.detector_rejected == 1
    assert len(res.df) == 1
    assert res.df_excluded is not None
    row = res.df_excluded.iloc[0]
    assert row["drop_stage"] == "detector"
    assert row["drop_reason"] == "plateau:rupture"
    assert res.anom is None
