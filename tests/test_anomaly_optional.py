"""Anomaly screening is optional and never changes detection boundaries."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from nanopore.analyze import analyze
from nanopore.anomaly import AnomalyRegion, AnomalyResult
from nanopore.config import PipelineConfig
from tests.synth import SynthEvent, make_signal


class _Rec:
    def __init__(self, sig):
        self.current = sig.current
        self.sample_rate_hz = sig.sample_rate_hz
        self.path = Path("synth_anomaly_optional.abf")
        self.protocol_voltage = None


def _signal():
    return make_signal(
        [SynthEvent(start_s=1.0, duration_s=0.5, amplitude_pA=-50.0),
         SynthEvent(start_s=3.0, duration_s=0.4, amplitude_pA=-50.0)],
        duration_s=6.0, seed=2,
    )


def _force_region(monkeypatch, sig):
    def _fake(*_args, **_kwargs):
        valid = np.ones(len(sig.current), dtype=bool)
        return AnomalyResult(
            [AnomalyRegion("membrane_rupture", 0.95, 1.55)],
            valid, np.array([]), 0.1, sig.baseline_pA,
        )

    monkeypatch.setattr("nanopore.analyze.detect_anomalies", _fake)


def _spans(res):
    return [(e.start_s, e.end_s, e.amplitude_pA) for e in res.det.events]


def test_anomaly_switch_does_not_change_detection(monkeypatch):
    sig = _signal()
    _force_region(monkeypatch, sig)
    base = PipelineConfig(level0=100.0, level1=50.0, min_toff_ms=0.0)
    with_anomaly = PipelineConfig(level0=100.0, level1=50.0, min_toff_ms=0.0,
                                  enabled_mods=("anomaly",))

    plain = analyze(_Rec(sig), base)
    screened = analyze(_Rec(sig), with_anomaly)

    assert _spans(plain) == _spans(screened)
    assert plain.anomaly_enabled is False
    assert screened.anomaly_enabled is True
    assert len(plain.df) == 2
    assert len(screened.df) == 1
    assert screened.df_excluded is not None
    assert "anomaly" in set(screened.df_excluded["drop_stage"])


def test_burst_detection_is_identical_with_anomaly_on(monkeypatch):
    sig = _signal()
    _force_region(monkeypatch, sig)
    base = PipelineConfig(detector="burst", level0=100.0, level1=50.0,
                          min_toff_ms=0.0)
    combined = PipelineConfig(detector="burst", level0=100.0, level1=50.0,
                              min_toff_ms=0.0, enabled_mods=("anomaly",))

    plain = analyze(_Rec(sig), base)
    screened = analyze(_Rec(sig), combined)

    assert _spans(plain) == _spans(screened)
    assert plain.det.diagnostics == screened.det.diagnostics
    assert plain.det.i0_used and screened.det.i0_used


def test_analyze_reports_actual_detector_and_optional_mods():
    sig = _signal()
    cfg = PipelineConfig(detector="plateau", level0=100.0, level1=50.0,
                         min_toff_ms=0.0, enabled_mods=("dynamic_i0",))
    res = analyze(_Rec(sig), cfg)
    assert res.detector_id == "plateau"
    assert res.anomaly_enabled is False
    assert res.enabled_mods == ("dynamic_i0",)
    assert res.i0_used is False          # plateau does not consume dynamic I0
    assert res.i0_profile is not None    # but it remains available to features
