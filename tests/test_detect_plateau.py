"""Regression tests for the event-stability (plateau) gate.

A fast flicker — a run that keeps returning to baseline for sub-ignore blips —
merges into ONE event whose body oscillates across levels. The plain spike/
dwell checks pass it, but its "plateau fraction" (samples dwelling on the single
level nearest the body median) is ~0.5, while a flat blockade sits at ~1.0.
``plateau_min_frac`` rejects the oscillator; 0 (default) leaves everything alone.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from nanopore.analyze import analyze
from nanopore.config import PipelineConfig
from nanopore.detect import detect_events, resolve_detector_id
from nanopore.detect_plateau import detect_plateau
from nanopore.io import AbfRecording

SR = 10_000.0
BASE, LEVEL = 100.0, 50.0     # 50 pA downward blockade on a 100 pA baseline


def _sig(duration_s: float, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(duration_s * SR)
    return BASE + rng.normal(0.0, 0.8, n)


def _detect(sig, plateau: float):
    return detect_events(sig, SR, BASE, LEVEL, polarity=-1, cutoff_hz=None,
                         plateau_min_frac=plateau)


def test_flat_blockade_survives_the_gate():
    """A clean flat blockade (plateau ~1.0) is kept whether the gate is on or off."""
    sig = _sig(2.0)
    sig[int(1.0 * SR):int(1.1 * SR)] = LEVEL          # 100 ms flat blockade
    off = _detect(sig, 0.0).events
    on = _detect(sig, 0.85).events

    assert len(off) == 1 and len(on) == 1, (len(off), len(on))
    assert abs(off[0].dwell_s - 0.1) < 5e-3


def test_flicker_is_rejected_by_the_gate_only():
    """A 100 ms run whose excursions dwell at the event level (3 ms) with short
    sub-ignore returns to baseline (1.5 ms) merges into ONE event; the gate
    (0.85) rejects it, the default (0) keeps it."""
    sig = _sig(2.0)
    a, b = int(1.0 * SR), int(1.1 * SR)
    osc = np.tile(np.concatenate([np.full(30, LEVEL), np.full(15, BASE)]), 50)
    sig[a:b] = osc[: b - a]

    off = _detect(sig, 0.0).events
    on = _detect(sig, 0.85).events

    assert len(off) >= 1, "sanity: the flicker must be detected when the gate is off"
    assert len(on) == 0, f"gate should reject the flicker, kept {[e.dwell_s for e in on]}"


def test_gate_default_is_off():
    """Omitting plateau_min_frac must reproduce the ungated result exactly."""
    sig = _sig(2.0)
    sig[int(1.0 * SR):int(1.1 * SR)] = LEVEL
    default = detect_events(sig, SR, BASE, LEVEL, polarity=-1, cutoff_hz=None).events
    off = _detect(sig, 0.0).events

    assert [(e.start_s, e.end_s) for e in default] == [(e.start_s, e.end_s) for e in off]


# ---------------------------------------------------------------------------
# Platform-hysteresis detector (detector="plateau", ported from npsweep)
# ---------------------------------------------------------------------------

PFS = 25_000.0
PBASE = 370.0   # open pore; events at 250 pA are depth 120 (not rupture)


def _ptr(events, duration_s=1.0, noise=1.0, seed=0):
    """events: list of (start_s, end_s, absolute level pA)."""
    n = int(round(duration_s * PFS))
    x = np.full(n, PBASE, dtype=float)
    for a, b, level in events:
        x[int(round(a * PFS)):int(round(b * PFS))] = level
    rng = np.random.default_rng(seed)
    return x + rng.normal(0.0, noise, n)


def test_plateau_partial_recovery_stays_one_event():
    # long blockade with a 5 ms partial recovery to 80 pA (20 pA from the pore)
    x = _ptr([(0.20, 0.34, 250.0), (0.34, 0.345, 330.0), (0.345, 0.50, 250.0),
              (0.70, 0.72, 250.0)])
    p = detect_plateau(x, PFS, PBASE, direction="down",
                       enter_depth_pA=60.0, exit_depth_pA=15.0, min_open_ms=1.0)
    assert len(p.events) == 2
    long_ev = max(p.events, key=lambda e: e.dwell_s)
    assert abs(long_ev.start_s - 0.20) < 0.002
    assert abs(long_ev.end_s - 0.50) < 0.002

    # the level method cuts at the 50% crossing (90 pA), so the partial recovery
    # to 80 pA is baseline -> the long event is split
    lv = detect_events(x, PFS, PBASE, 250.0, polarity=-1,
                       ignore_duration_ms=0.5, ignore_event_duration_ms=1.0)
    assert len(lv.events) >= 3


def test_plateau_upward_and_both_directions():
    x = _ptr([(0.20, 0.30, 490.0), (0.60, 0.70, 250.0)])
    up = detect_plateau(x, PFS, PBASE, direction="up",
                        enter_depth_pA=60.0, exit_depth_pA=15.0)
    assert len(up.events) == 1
    assert up.events[0].depth_pA > 0
    both = detect_plateau(x, PFS, PBASE, direction="both",
                          enter_depth_pA=60.0, exit_depth_pA=15.0)
    assert len(both.events) == 2


def test_plateau_rupture_is_dropped():
    x = _ptr([(0.30, 0.40, 0.0)])
    p = detect_plateau(x, PFS, PBASE, direction="down",
                       enter_depth_pA=60.0, exit_depth_pA=15.0,
                       exclude_rupture=True)
    assert len(p.events) == 0
    kept = detect_plateau(x, PFS, PBASE, direction="down",
                          enter_depth_pA=60.0, exit_depth_pA=15.0,
                          exclude_rupture=False)
    assert len(kept.events) == 1


def test_plateau_pulse_cleared_is_dropped():
    x = _ptr([(0.30, 0.40, 250.0)])
    voltage = np.zeros_like(x)
    voltage[int(0.40 * PFS):int(0.50 * PFS)] = 100.0
    p = detect_plateau(x, PFS, PBASE, voltage=voltage, direction="down",
                       enter_depth_pA=60.0, exit_depth_pA=15.0,
                       exclude_pulse_cleared=True, pulse_tol_ms=50.0)
    assert len(p.events) == 0


def test_detector_id_resolution():
    assert resolve_detector_id(PipelineConfig(detector="plateau")) == "plateau"
    assert resolve_detector_id(PipelineConfig(event_mode="burst")) == "burst"
    assert resolve_detector_id(PipelineConfig()) == "level"


def test_analyze_with_plateau():
    x = _ptr([(0.20, 0.50, 250.0), (0.70, 0.72, 250.0)])
    rec = AbfRecording(path=Path("synth.abf"), current=x,
                       sample_rate_hz=PFS, units="pA",
                       n_channels=1, sweep_count=1)
    cfg = PipelineConfig(detector="plateau", level0=PBASE, level1=250.0,
                         polarity=-1, plateau_direction="down",
                         min_toff_ms=0.0, enabled_mods=())
    res = analyze(rec, cfg)
    assert len(res.det.events) == 2
    assert len(res.df) == 2
    assert {"t1", "t2", "toff", "I0", "mean"} <= set(res.df.columns)
