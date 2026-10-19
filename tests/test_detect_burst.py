"""Dwell-envelope burst detector (event_mode="burst") — synthetic ground truth.

These cases pin the two behaviours the mode exists for: a single dwell with
glitches/overshoots, and baseline-hopping multi-level signals, without touching
the default level-mode path.
"""

import numpy as np
import pytest

from nanopore.config import PipelineConfig
from nanopore.detect import detect, detect_events, detect_events_burst

SR = 25_000.0


def _sig(duration_s=1.0, baseline=100.0):
    return np.full(int(duration_s * SR), baseline)


def _set(cur, t0, t1, value):
    cur[int(t0 * SR):int(t1 * SR)] = value


def _burst(cur, **kw):
    kw.setdefault("polarity", -1)
    return detect_events_burst(cur, SR, 100.0, 40.0, **kw)


def _dwells(res):
    return [(round(e.start_s, 3), round(e.end_s, 3)) for e in res.events]


# ---- single dwell, glitches and overshoots -----------------------------
def test_short_returns_keep_one_event():
    cur = _sig()
    _set(cur, 0.10, 0.60, 40.0)                  # one dwell
    for t0, t1 in ((0.20, 0.205), (0.30, 0.308), (0.40, 0.402)):
        _set(cur, t0, t1, 100.0)                 # brief returns to open
    r = _burst(cur, min_gap_ms=30, min_block_ms=2)
    assert len(r.events) == 1
    assert r.events[0].start_s == pytest.approx(0.10, abs=1e-3)


def test_overshoot_past_open_keeps_one_event():
    cur = _sig()
    _set(cur, 0.10, 0.60, 40.0)
    _set(cur, 0.30, 0.305, 130.0)                # 5 ms overshoot PAST open
    r = _burst(cur, min_gap_ms=30)
    assert len(r.events) == 1


def test_return_longer_than_gap_splits():
    cur = _sig()
    _set(cur, 0.10, 0.60, 40.0)
    _set(cur, 0.30, 0.360, 100.0)                # 60 ms return to open
    merged = _burst(cur, min_gap_ms=100)
    split = _burst(cur, min_gap_ms=30)
    assert len(merged.events) == 1
    assert len(split.events) == 2
    # level mode (bridge 50 ms) also splits this one
    lvl = detect_events(cur, SR, 100.0, 40.0, polarity=-1,
                        ignore_duration_ms=2, ignore_event_duration_ms=50)
    assert len(lvl.events) == 2


# ---- multi-level / baseline crossing -----------------------------------
def test_cross_baseline_merges_both_sides():
    cur = _sig()
    _set(cur, 0.20, 0.30, 40.0)                  # below open pore
    _set(cur, 0.30, 0.35, 130.0)                 # 50 ms ABOVE open pore
    _set(cur, 0.35, 0.60, 40.0)                  # below again
    both = _burst(cur, cross_baseline=True, min_gap_ms=30)
    one_side = _burst(cur, cross_baseline=False, min_gap_ms=30)
    assert len(both.events) == 1                 # one crossing event
    assert len(one_side.events) == 2             # the above-baseline stretch splits it


def test_cross_baseline_is_off_by_default():
    cur = _sig()
    _set(cur, 0.30, 0.40, 130.0)                 # a purely upward excursion
    assert len(_burst(cur).events) == 0          # downward search ignores it


# ---- anti-overmerge / spike floor / boundaries -------------------------
def test_two_real_events_stay_separate():
    cur = _sig()
    _set(cur, 0.10, 0.20, 40.0)
    _set(cur, 0.60, 0.70, 40.0)                  # 400 ms gap >> min_gap
    r = _burst(cur, min_gap_ms=30)
    assert len(r.events) == 2


def test_lone_spike_is_dropped():
    cur = _sig()
    _set(cur, 0.30, 0.301, 40.0)                 # 1 ms spike < min_block 2 ms
    r = _burst(cur, min_block_ms=2)
    assert len(r.events) == 0


def test_boundary_events_ignored():
    cur = _sig()
    _set(cur, 0.0, 0.20, 40.0)                   # touches record start
    _set(cur, 0.80, 1.0, 40.0)                   # touches record end
    r = _burst(cur)
    assert len(r.events) == 0


# ---- dispatcher: level mode is byte-for-byte the old path --------------
def test_dispatch_level_mode_matches_detect_events():
    cur = _sig()
    _set(cur, 0.10, 0.20, 40.0)
    _set(cur, 0.60, 0.70, 40.0)

    class _LV:
        level0 = 100.0
        level1 = 40.0
        polarity = -1

    cfg = PipelineConfig(event_mode="level")
    a = detect(cur, SR, _LV(), cfg)
    b = detect_events(
        cur, SR, 100.0, 40.0,
        ignore_duration_ms=cfg.ignore_duration_ms,
        ignore_event_duration_ms=cfg.ignore_event_duration_ms,
        level_contribution=cfg.level_contribution,
        update_levels=cfg.update_levels,
        polarity=-1,
        cutoff_hz=None,
        pre_event_ms=cfg.pre_event_ms,
        dwell_min_frac=cfg.dwell_min_frac,
        plateau_min_frac=cfg.event_plateau_min_frac,
    )
    assert _dwells(a) == _dwells(b)
    assert [e.amplitude_pA for e in a.events] == [e.amplitude_pA for e in b.events]


def test_dispatch_burst_mode():
    cur = _sig()
    _set(cur, 0.10, 0.60, 40.0)

    class _LV:
        level0 = 100.0
        level1 = 40.0
        polarity = -1

    cfg = PipelineConfig(event_mode="burst", burst_min_gap_ms=30)
    r = detect(cur, SR, _LV(), cfg)
    assert len(r.events) == 1
