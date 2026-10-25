"""Phase 4: direction-aware edges, integer boundaries, BIC diagnostics.

Synthetic signals with analytic truth; no local .abf data required.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from nanopore.io import AbfRecording
from nanopore.steps import (detect_steps, edge_bounds, edge_window_samples,
                            effective_sample_size)


def _rec(current: np.ndarray, fs: float = 25_000.0) -> AbfRecording:
    return AbfRecording(path=Path("synthetic.abf"), current=current,
                        sample_rate_hz=fs, units="pA", n_channels=1,
                        sweep_count=1)


def _block(n: int, fs: float, base: float = 100.0, level: float = 160.0,
           start: int = 0, end: int = 2_000, sigma: float = 1.0,
           seed: int = 0) -> np.ndarray:
    """Event body: the blockade starts at sample 0 and ends at ``end``.

    ``edge_bounds`` receives the body only (event start to event end), so the
    entry transition is at the beginning and the exit at ``end``.
    """
    rng = np.random.default_rng(seed)
    body = base + rng.normal(0.0, sigma, n)
    body[start:end] = level + rng.normal(0.0, sigma, end - start)
    return body


# --------------------------------------------------------------------------- #
# Edge trimming
# --------------------------------------------------------------------------- #

def test_edge_window_is_a_physical_time():
    assert edge_window_samples(25_000.0) == 5
    assert edge_window_samples(50_000.0) == 10
    # legacy sample-count override only applies when the time window is off
    assert edge_window_samples(50_000.0, win_ms=None, win=7) == 7


def test_upward_event_returns_from_above():
    fs = 25_000.0
    body = _block(4_000, fs, level=160.0)
    t_in, t_out = edge_bounds(body, 1.0, fs, 100.0, direction=1)
    assert t_in <= 40
    assert 1_900 <= t_out <= 2_100

    # A downward criterion is wrong for an upward event: nothing ever comes
    # back below the open pore, so the exit is not found.
    _, t_out_wrong = edge_bounds(body, 1.0, fs, 100.0, direction=-1)
    assert t_out_wrong > 3_900


def test_downward_event_returns_from_below():
    fs = 25_000.0
    body = _block(4_000, fs, level=40.0)
    t_in, t_out = edge_bounds(body, 1.0, fs, 100.0, direction=-1)
    assert t_in <= 40
    assert 1_900 <= t_out <= 2_100

    _, t_out_wrong = edge_bounds(body, 1.0, fs, 100.0, direction=1)
    assert t_out_wrong > 3_900


def test_bidirectional_event_returns_into_the_band():
    fs = 25_000.0
    rng = np.random.default_rng(1)
    body = 100.0 + rng.normal(0.0, 1.0, 4_000)
    body[0:1_000] = 140.0 + rng.normal(0.0, 1.0, 1_000)
    body[1_000:2_000] = 60.0 + rng.normal(0.0, 1.0, 1_000)
    t_in, t_out = edge_bounds(body, 1.0, fs, 100.0, direction=0)
    assert t_in <= 40
    assert 1_900 <= t_out <= 2_100


def test_baseline_ambiguity_flag_for_two_sided_body():
    from nanopore.fingerprint import (baseline_is_ambiguous,
                                      blockade_percentile)

    rng = np.random.default_rng(2)
    body = 100.0 + rng.normal(0.0, 1.0, 2_000)
    body[500:1_000] = 150.0
    body[1_000:1_500] = 50.0
    assert blockade_percentile(1) == 85.0
    assert blockade_percentile(-1) == 15.0
    assert baseline_is_ambiguous(body, 100.0, 1.0, direction=0)
    assert not baseline_is_ambiguous(body[:1_000], 100.0, 1.0, direction=-1)


# --------------------------------------------------------------------------- #
# Integer boundaries and coverage
# --------------------------------------------------------------------------- #

def test_detect_steps_uses_integer_boundaries_and_folds_the_remainder():
    rng = np.random.default_rng(3)
    n = 1_003
    body = 100.0 + rng.normal(0.0, 1.0, n)
    body[300:700] = 60.0 + rng.normal(0.0, 1.0, 400)

    steps, _k, decim = detect_steps(
        body, 25_000.0, 100.0, sigma_pA=1.0, k_max=8,
        tau_min_us=10.0, amp_min=2.0, n_dp_max=200,
    )
    assert decim == 6                       # ceil(1003 / 200)
    assert steps[0].start == 0
    assert steps[-1].end == n                # the dropped remainder is folded in
    assert all(a.end == b.start for a, b in zip(steps, steps[1:]))
    assert sum(s.length for s in steps) == n
    assert abs(sum(s.tau_s for s in steps) - n / 25_000.0) < 1e-12


def test_describer_covers_the_whole_trimmed_body():
    from nanopore.analyze import AnalysisResult
    from nanopore.config import PipelineConfig
    from nanopore.fingerprint import describe_result

    fs = 25_000.0
    rng = np.random.default_rng(4)
    n = 1_003
    s, e = 5_000, 5_000 + n
    current = 100.0 + rng.normal(0.0, 1.0, 12_000)
    current[s:e] = 60.0 + rng.normal(0.0, 1.0, n)
    rec = _rec(current, fs)
    cfg = PipelineConfig(enabled_mods=("describe",),
                         describe_params={"n_dp_max": 200})
    df = pd.DataFrame([{"t1": s / fs, "t2": e / fs, "Io": 100.0,
                        "mean": -40.0, "state": "A"}])
    res = AnalysisResult(rec, None, current, None, None, None, df, None,
                         detector_id="level", enabled_mods=("describe",),
                         config=cfg)
    desc = describe_result(res)[0]

    assert desc.features["coverage_trimmed_frac"] == 1.0
    assert desc.segments[-1].end == int(desc.features["edge_out_samples"])
    assert desc.segments[0].start == int(desc.features["edge_in_samples"])
    assert all(a.end == b.start for a, b in zip(desc.segments,
                                                desc.segments[1:]))


# --------------------------------------------------------------------------- #
# BIC over-segmentation diagnostics
# --------------------------------------------------------------------------- #

def _autocorrelated_multistep(n: int = 12_000, seed: int = 5) -> np.ndarray:
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    body = 100.0 - 20.0 * (t / n)
    body[3_000:7_000] -= 8.0
    body[7_000:9_000] -= 6.0
    kernel = np.ones(41) / 41
    return body + np.convolve(rng.normal(0.0, 1.2, n), kernel, mode="same")


def test_effective_sample_size_distinguishes_white_from_smoothed_noise():
    rng = np.random.default_rng(6)
    white = rng.normal(0.0, 1.0, 4_000)
    assert effective_sample_size(white) > 0.8 * white.size

    smooth = np.convolve(white, np.ones(41) / 41, mode="same")
    assert effective_sample_size(smooth) < 0.1 * smooth.size


def test_effective_sample_size_bic_reduces_over_segmentation():
    body = _autocorrelated_multistep()
    common = dict(sigma_pA=1.2, k_max=30, tau_min_us=250.0, amp_min=2.0)
    base, _k, _d = detect_steps(body, 25_000.0, 100.0, bic_n_eff=0, **common)
    auto, _k2, _d2 = detect_steps(body, 25_000.0, 100.0, bic_n_eff=-1, **common)

    # The default (source) behaviour treats autocorrelated points as
    # independent and over-segments; the autocorrelation-aware BIC keeps the
    # real structure and drops the spurious pieces.
    assert len(base) > len(auto)
    assert len(auto) <= 4


def test_bic_penalty_monotonically_suppresses_complexity():
    from nanopore.steps import _dp_fit, _bic_k

    body = _autocorrelated_multistep()
    rss, _backs = _dp_fit(body, 30)
    neff = effective_sample_size(body)
    k_auto = _bic_k(rss, body.size, n_eff=neff, penalty=1.0)
    k_strong = _bic_k(rss, body.size, n_eff=neff, penalty=3.0)
    assert k_strong <= k_auto


# --------------------------------------------------------------------------- #
# Classic describer and interval evaluation
# --------------------------------------------------------------------------- #

def test_classic_describer_finds_a_pulse_above_the_blockade_baseline():
    from nanopore.analyze import AnalysisResult
    from nanopore.config import PipelineConfig
    from nanopore.fingerprint import describe_result, get_describer

    fs = 25_000.0
    rng = np.random.default_rng(7)
    n = 8_000
    s, e = 2_000, 4_000
    current = 100.0 + rng.normal(0.0, 1.0, n)
    current[s:e] = 20.0 + rng.normal(0.0, 1.0, e - s)     # blocked baseline
    current[s + 600:s + 1_100] = 60.0                     # fingerprint pulse
    rec = _rec(current, fs)
    cfg = PipelineConfig(enabled_mods=("describe",), describer="classic")
    df = pd.DataFrame([{"t1": s / fs, "t2": e / fs, "Io": 100.0,
                        "mean": -80.0, "state": "A"}])
    res = AnalysisResult(rec, None, current, None, None, None, df, None,
                         detector_id="level", enabled_mods=("describe",),
                         config=cfg)
    desc = describe_result(res)[0]
    classic = get_describer("classic")

    assert classic.maturity == "beta"
    assert len(desc.segments) == 1
    seg = desc.segments[0]
    assert abs(seg.level_pA - 60.0) < 3.0
    assert abs(seg.start - 600) < 60
    assert abs(seg.end - 1_100) < 60


def test_global_intervals_and_interval_evaluation():
    from types import SimpleNamespace

    from nanopore.fingerprint import (Segment, evaluate_intervals,
                                      to_global_intervals,
                                      to_global_intervals_by_event)

    desc = SimpleNamespace(
        event_id=1, event_start=1_000,
        segments=[Segment(start=0, end=100, start_global=1_000,
                          end_global=1_100),
                  Segment(start=200, end=300, start_global=1_200,
                          end_global=1_300)],
    )
    assert to_global_intervals(desc) == [(1_000, 1_100), (1_200, 1_300)]
    assert to_global_intervals_by_event([desc]) == {
        1: [(1_000, 1_100), (1_200, 1_300)]}

    fs = 25_000.0
    preds = {1: [(1_000, 1_100), (1_200, 1_300)]}
    truths = {1: [(1_005, 1_095), (1_210, 1_310)]}
    rep = evaluate_intervals(preds, truths, fs, tols_ms=(0.25, 0.5))
    # 0.25 ms = 6.25 samples: the first pair (5 samples off) matches, the
    # second (10 samples off) does not.
    assert rep.interval_f1[0.25][3] == 1
    # 0.5 ms = 12.5 samples: both pairs match.
    assert rep.interval_f1[0.5][0] == 1.0
    assert rep.summary()["n_missed"] == 0


def test_interval_evaluation_reports_misses_and_spurious():
    from nanopore.fingerprint import evaluate_intervals

    fs = 25_000.0
    preds = {1: [(0, 100), (500, 600)]}
    truths = {1: [(0, 100), (300, 400)]}
    rep = evaluate_intervals(preds, truths, fs, tols_ms=(0.5,))
    assert rep.interval_f1[0.5][3] == 1
    assert rep.summary()["n_missed"] == 1
    assert rep.summary()["n_spurious"] == 1


# --------------------------------------------------------------------------- #
# Event-shape acceptance: shallow, slow exit, upward, bidirectional
# --------------------------------------------------------------------------- #

def _analysis(current, s, e, fs=25_000.0, mean=-40.0, i_open=100.0,
              params=None):
    from nanopore.analyze import AnalysisResult
    from nanopore.config import PipelineConfig

    rec = _rec(current, fs)
    cfg = PipelineConfig(enabled_mods=("describe",),
                         describe_params=dict(params or {}))
    df = pd.DataFrame([{"t1": s / fs, "t2": e / fs, "Io": i_open,
                        "mean": mean, "state": "A"}])
    return AnalysisResult(rec, None, current, None, None, None, df, None,
                          detector_id="level", enabled_mods=("describe",),
                          config=cfg)


def test_shallow_event_has_no_transition_segments():
    from nanopore.fingerprint import describe_result

    fs = 25_000.0
    rng = np.random.default_rng(8)
    s, e = 5_000, 7_000
    current = 100.0 + rng.normal(0.0, 1.0, 12_000)
    current[s:e] = 85.0 + rng.normal(0.0, 1.0, e - s)   # 15 pA deep
    desc = describe_result(_analysis(current, s, e, fs, mean=-15.0))[0]

    assert len(desc.segments) == 1
    assert abs(desc.segments[0].level_pA - 85.0) < 2.0
    assert desc.features["coverage_trimmed_frac"] == 1.0


def test_single_step_event_recovers_two_levels():
    from nanopore.fingerprint import describe_result

    fs = 25_000.0
    rng = np.random.default_rng(12)
    s, e = 5_000, 7_000
    mid = s + (e - s) // 2
    current = 100.0 + rng.normal(0.0, 1.0, 12_000)
    current[s:mid] = 60.0 + rng.normal(0.0, 1.0, mid - s)
    current[mid:e] = 20.0 + rng.normal(0.0, 1.0, e - mid)
    desc = describe_result(_analysis(current, s, e, fs, mean=-60.0))[0]

    assert len(desc.segments) == 2
    levels = [seg.level_pA for seg in desc.segments]
    assert abs(levels[0] - 60.0) < 2.0
    assert abs(levels[1] - 20.0) < 2.0


def test_long_event_filling_most_of_the_context_has_full_trimmed_coverage():
    from nanopore.fingerprint import describe_result

    fs = 25_000.0
    rng = np.random.default_rng(13)
    n = 9_000
    s, e = 0, 8_000                 # body is ~89% of the context window
    current = 100.0 + rng.normal(0.0, 1.0, n)
    current[s:e] = 40.0 + rng.normal(0.0, 1.0, e - s)
    desc = describe_result(_analysis(current, s, e, fs, mean=-60.0))[0]

    assert len(desc.segments) == 1
    assert desc.features["coverage_trimmed_frac"] == 1.0
    assert desc.coverage["coverage_frac"] > 0.95


def test_slow_exit_ramp_is_trimmed_from_the_description():
    from nanopore.fingerprint import describe_result

    fs = 25_000.0
    rng = np.random.default_rng(9)
    s, e = 5_000, 6_300
    current = 100.0 + rng.normal(0.0, 1.0, 12_000)
    current[s:s + 1_000] = 40.0 + rng.normal(0.0, 1.0, 1_000)
    ramp = np.linspace(40.0, 100.0, 300)
    current[s + 1_000:e] = ramp + rng.normal(0.0, 1.0, 300)
    desc = describe_result(_analysis(current, s, e, fs, mean=-60.0))[0]

    # The stable blockade is one segment; the exit ramp is not reported as
    # extra constant levels, and the description still covers its own body.
    assert len(desc.segments) == 1
    assert abs(desc.segments[0].level_pA - 40.0) < 3.0
    assert desc.features["n_segments_raw"] > len(desc.segments)
    assert desc.features["edge_out_raw_samples"] > desc.features["edge_out_samples"]
    assert desc.features["coverage_trimmed_frac"] == 1.0


def test_upward_event_uses_the_upper_blockade_baseline():
    from nanopore.fingerprint import build_event_view, describe_result

    fs = 25_000.0
    rng = np.random.default_rng(10)
    s, e = 5_000, 7_000
    current = 100.0 + rng.normal(0.0, 1.0, 12_000)
    current[s:e] = 160.0 + rng.normal(0.0, 1.0, e - s)
    res = _analysis(current, s, e, fs, mean=+60.0)

    view = build_event_view(res, 0)
    assert view.direction == 1
    assert view.i_blockade > 150.0          # p85, not p15
    desc = describe_result(res)[0]
    assert len(desc.segments) == 1
    assert abs(desc.segments[0].level_pA - 160.0) < 3.0


def test_bidirectional_event_is_flagged_and_segmented_on_both_sides():
    from nanopore.fingerprint import build_event_view, describe_result

    fs = 25_000.0
    rng = np.random.default_rng(11)
    s, e = 5_000, 7_000
    current = 100.0 + rng.normal(0.0, 1.0, 12_000)
    current[s:s + 1_000] = 60.0 + rng.normal(0.0, 1.0, 1_000)
    current[s + 1_000:e] = 140.0 + rng.normal(0.0, 1.0, 1_000)
    res = _analysis(current, s, e, fs, mean=0.0)

    view = build_event_view(res, 0)
    assert view.direction == 0
    assert view.meta["baseline_ambiguous"] is True
    desc = describe_result(res)[0]
    assert desc.quality.get("baseline_ambiguous") is True
    assert len(desc.segments) == 2
    levels = sorted(seg.level_pA for seg in desc.segments)
    assert abs(levels[0] - 60.0) < 3.0
    assert abs(levels[1] - 140.0) < 3.0
