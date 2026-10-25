"""EventView context: the analysis trace, dynamic I0, voltage and coordinates."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from nanopore.io import AbfRecording
from tests.synth import SynthEvent, make_signal


def _rec(current: np.ndarray, fs: float = 25_000.0, voltage=None) -> AbfRecording:
    return AbfRecording(path=Path("synthetic.abf"), current=current,
                        sample_rate_hz=fs, units="pA", n_channels=1,
                        sweep_count=1, voltage=voltage)


def _one_event(amplitude: float = -50.0, seed: int = 3):
    return make_signal([SynthEvent(1.0, 0.10, amplitude)], duration_s=3.0,
                       sample_rate_hz=25_000.0, noise_sigma_pA=1.0, seed=seed)


def test_view_uses_the_analysis_trace_when_lowpass_is_on():
    from nanopore.analyze import analyze
    from nanopore.config import PipelineConfig
    from nanopore.fingerprint import build_event_view
    from nanopore.preprocess import lowpass

    sig = _one_event()
    rec = _rec(sig.current)
    cfg = PipelineConfig(enabled_mods=("lowpass", "describe"),
                         filter_lowpass_hz=2_000.0)
    res = analyze(rec, cfg)
    assert len(res.df) == 1

    view = build_event_view(res, 0)
    filtered = lowpass(rec.current, rec.sample_rate_hz, cfg.filter_lowpass_hz)
    assert np.array_equal(view.analysis, filtered[view.ctx_start:view.ctx_end])
    assert np.array_equal(view.raw, rec.current[view.ctx_start:view.ctx_end])
    assert not np.array_equal(view.analysis, view.raw)
    assert view.trace_source == "analysis"
    assert view.lowpass_hz == pytest.approx(2_000.0)
    assert np.array_equal(view.current, view.analysis)


def test_view_uses_the_dynamic_i0_window():
    from nanopore.analyze import analyze
    from nanopore.config import PipelineConfig
    from nanopore.fingerprint import build_event_view

    sig = _one_event()
    rec = _rec(sig.current)
    res = analyze(rec, PipelineConfig(enabled_mods=("dynamic_i0", "describe")))
    view = build_event_view(res, 0)

    assert res.i0_profile is not None
    assert np.array_equal(view.i0_profile,
                          res.i0_profile.baseline[view.ctx_start:view.ctx_end])
    assert view.i_open == pytest.approx(float(res.df.iloc[0]["Io"]))
    assert view.i_open_source == "feature:Io"
    assert np.isfinite(view.i_blockade) and np.isfinite(view.sigma_open)


def test_view_slices_the_voltage_trace():
    from nanopore.analyze import analyze
    from nanopore.config import PipelineConfig
    from nanopore.fingerprint import build_event_view

    sig = _one_event()
    voltage = np.full(sig.current.size, 100.0)
    voltage[sig.current.size // 2:] = -50.0
    rec = _rec(sig.current, voltage=voltage)
    res = analyze(rec, PipelineConfig(enabled_mods=("describe",)))
    view = build_event_view(res, 0)

    assert view.voltage is not None
    assert np.array_equal(view.voltage, voltage[view.ctx_start:view.ctx_end])


def test_view_global_coordinates_direction_and_key():
    from nanopore.analyze import analyze
    from nanopore.config import PipelineConfig
    from nanopore.fingerprint import build_event_view, event_key

    sig = _one_event(amplitude=-50.0)
    rec = _rec(sig.current)
    res = analyze(rec, PipelineConfig(enabled_mods=("describe",)))
    view = build_event_view(res, 0)
    row = res.df.iloc[0]

    assert view.start == int(round(float(row["t1"]) * rec.sample_rate_hz))
    assert view.end == int(round(float(row["t2"]) * rec.sample_rate_hz))
    assert view.ctx_start <= view.start and view.ctx_end >= view.end
    assert view.direction == -1
    assert view.event_key == event_key(view.source_id, view.fs, view.start, view.end)
    assert view.detector_id == "level"
    assert view.detector_params["dwell_min_frac"] == pytest.approx(0.30)
    assert view.analysis_params["filter_lowpass_hz"] is None


def test_upward_event_direction():
    from nanopore.analyze import analyze
    from nanopore.config import PipelineConfig
    from nanopore.fingerprint import build_event_view

    sig = _one_event(amplitude=+50.0)
    res = analyze(_rec(sig.current), PipelineConfig(enabled_mods=("describe",)))
    assert len(res.df) == 1
    assert build_event_view(res, 0).direction == 1


def _three_step_analysis(seed: int = 0):
    from nanopore.analyze import AnalysisResult
    from nanopore.config import PipelineConfig

    fs = 50_000.0
    rng = np.random.default_rng(seed)
    current = np.full(30_000, 100.0) + rng.normal(0, 1.0, 30_000)
    s, e = 10_000, 12_000
    third = (e - s) // 3
    current[s:s + third] = 60.0
    current[s + third:s + 2 * third] = 20.0
    current[s + 2 * third:e] = 60.0
    rec = _rec(current, fs=fs)
    cfg = PipelineConfig(enabled_mods=("describe",))
    df = pd.DataFrame([{"t1": s / fs, "t2": e / fs, "Io": 100.0,
                        "mean": -40.0, "state": "A"}])
    return AnalysisResult(rec, None, current, None, None, None, df, None,
                          detector_id="level", enabled_mods=("describe",),
                          config=cfg)


def test_segments_carry_global_coordinates_and_coverage():
    from nanopore.fingerprint import describe_result

    res = _three_step_analysis()
    desc = describe_result(res)[0]

    assert len(desc.segments) == 3
    for seg in desc.segments:
        assert seg.start_global == desc.event_start + seg.start
        assert seg.end_global == desc.event_start + seg.end
    assert desc.coverage["event_samples"] == 2_000
    assert 0.9 <= desc.coverage["coverage_frac"] <= 1.0
    assert desc.attrs["direction"] == -1
    assert desc.analysis_params["detector"] == "level"


def test_invalid_description_reports_zero_coverage():
    from nanopore.analyze import AnalysisResult
    from nanopore.config import PipelineConfig
    from nanopore.fingerprint import describe_result

    fs = 25_000.0
    current = np.full(2_000, 100.0)
    rec = _rec(current, fs=fs)
    df = pd.DataFrame([{"t1": 0.04, "t2": 0.04008, "Io": 100.0,
                        "mean": -50.0, "state": "A"}])   # 2 samples
    res = AnalysisResult(rec, None, current, None, None, None, df, None,
                         detector_id="level", enabled_mods=("describe",),
                         config=PipelineConfig(enabled_mods=("describe",)))
    desc = describe_result(res)[0]

    assert desc.quality["valid"] is False
    assert desc.segments == []
    assert desc.coverage["covered_samples"] == 0
    assert desc.coverage["coverage_frac"] == 0.0


def test_legacy_row_view_declares_the_raw_trace():
    from nanopore.describe import make_event_view

    sig = _one_event()
    rec = _rec(sig.current)
    row = {"t1": 1.0, "t2": 1.1, "Io": 100.0, "state": "A"}
    view = make_event_view(rec, row, event_id=7)

    assert view.event_id == 7 and view.legacy_event_id == 7
    assert view.trace_source == "raw"
    assert np.array_equal(view.current, rec.current[view.ctx_start:view.ctx_end])
    assert view.event_key
