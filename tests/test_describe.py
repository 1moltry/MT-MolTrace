"""Event description layer: contract, DP+BIC recovery, writers, integration."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from nanopore.io import AbfRecording
from tests.synth import SynthEvent, make_signal


def _rec(current: np.ndarray, fs: float = 50_000.0) -> AbfRecording:
    return AbfRecording(path=Path("synthetic.abf"), current=current,
                        sample_rate_hz=fs, units="pA", n_channels=1,
                        sweep_count=1)


def _three_step_event(fs: float = 50_000.0, n: int = 30_000,
                      start: int = 10_000, end: int = 12_000):
    rng = np.random.default_rng(0)
    current = np.full(n, 100.0) + rng.normal(0, 1.0, n)
    third = (end - start) // 3
    current[start:start + third] = 60.0 + rng.normal(0, 1.0, third)
    current[start + third:start + 2 * third] = 20.0 + rng.normal(0, 1.0, third)
    current[start + 2 * third:end] = 60.0 + rng.normal(0, 1.0, end - start - 2 * third)
    return current, start, end


def test_mod_registered():
    from nanopore.mods import resolve_mods

    assert resolve_mods(("describe",)) == ("describe",)


def test_event_view_contract():
    from nanopore.describe import make_event_view

    current, s, e = _three_step_event()
    rec = _rec(current)
    row = {"t1": s / rec.sample_rate_hz, "t2": e / rec.sample_rate_hz,
           "Io": 100.0, "state": "A"}
    view = make_event_view(rec, row, event_id=7)
    assert view.event_id == 7
    assert view.start == s and view.end == e
    assert view.ctx_start <= s and view.ctx_end >= e
    assert abs(view.i_open - 100.0) < 2.0
    assert abs(view.i_blockade - 20.0) < 3.0     # p15 of a 60/20/60 body
    assert 0.2 < view.sigma_open < 2.5
    assert view.body.size == e - s
    assert abs(view.duration_ms - 40.0) < 0.1


def test_dp_bic_recovers_three_steps():
    from nanopore.describe import describe_rows
    from nanopore.config import PipelineConfig

    current, s, e = _three_step_event()
    rec = _rec(current)
    df = pd.DataFrame([{"t1": s / rec.sample_rate_hz, "t2": e / rec.sample_rate_hz,
                        "Io": 100.0, "state": "A"}])
    desc = describe_rows(df, rec, PipelineConfig(enabled_mods=("describe",)))[0]

    assert desc.quality["valid"] is True
    assert len(desc.segments) == 3
    levels = [seg.level_pA for seg in desc.segments]
    assert abs(levels[0] - 60.0) < 2.0
    assert abs(levels[1] - 20.0) < 2.0
    assert abs(levels[2] - 60.0) < 2.0
    fs = rec.sample_rate_hz
    third_ms = (e - s) / 3 / fs * 1000.0
    assert abs(desc.segments[0].end / fs * 1000.0 - third_ms) < 2.0
    assert abs(desc.segments[1].end / fs * 1000.0 - 2 * third_ms) < 2.0


def test_snr_gate_can_merge_segments():
    from nanopore.config import PipelineConfig
    from nanopore.describe import describe_rows

    current, s, e = _three_step_event()
    rec = _rec(current)
    df = pd.DataFrame([{"t1": s / rec.sample_rate_hz, "t2": e / rec.sample_rate_hz,
                        "Io": 100.0, "state": "A"}])
    cfg = PipelineConfig(enabled_mods=("describe",),
                         describe_params={"snr_min": 1e6})
    desc = describe_rows(df, rec, cfg)[0]
    assert len(desc.segments) == 1


def test_scalar_describer():
    from nanopore.config import PipelineConfig
    from nanopore.describe import describe_rows

    current, s, e = _three_step_event()
    rec = _rec(current)
    df = pd.DataFrame([{"t1": s / rec.sample_rate_hz, "t2": e / rec.sample_rate_hz,
                        "Io": 100.0, "state": "A"}])
    cfg = PipelineConfig(enabled_mods=("describe",), describer="scalar")
    desc = describe_rows(df, rec, cfg)[0]
    assert desc.segments == []
    assert abs(desc.features["dwell_ms"] - 40.0) < 0.1
    assert "skew_biased" in desc.features


def test_writers_roundtrip(tmp_path):
    from nanopore.analysis import write_fingerprints
    from nanopore.config import PipelineConfig
    from nanopore.describe import describe_rows

    current, s, e = _three_step_event()
    rec = _rec(current)
    df = pd.DataFrame([{"t1": s / rec.sample_rate_hz, "t2": e / rec.sample_rate_hz,
                        "Io": 100.0, "state": "A"}])
    descs = describe_rows(df, rec, PipelineConfig(enabled_mods=("describe",)))
    paths = write_fingerprints(descs, tmp_path, "demo", fs=rec.sample_rate_hz,
                               source="synthetic.abf")

    payload = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert payload["describer"] == "dp_bic"
    assert len(payload["events"]) == 1
    assert len(payload["events"][0]["segments"]) == 3

    sheets = pd.read_excel(paths["xlsx"], sheet_name=None)
    assert set(sheets) == {"events", "segments", "params"}
    assert len(sheets["segments"]) == 3
    assert abs(sheets["segments"]["width_ms"].sum() - 40.0) < 2.0


def test_analyze_describe_mod_integration():
    from nanopore.analyze import analyze
    from nanopore.config import PipelineConfig

    sig = make_signal([SynthEvent(1.0, 0.02, -50)], duration_s=3.0,
                      sample_rate_hz=25_000, noise_sigma_pA=1.0, seed=21)
    rec = _rec(sig.current, sig.sample_rate_hz)
    cfg = PipelineConfig(enabled_mods=("describe",))
    res = analyze(rec, cfg)

    assert len(res.df) == 1
    assert res.descs is not None and len(res.descs) == len(res.df)
    assert res.descs[0].event_id == 1
    assert res.descs[0].segments


def test_describe_off_by_default():
    from nanopore.analyze import analyze
    from nanopore.config import PipelineConfig

    sig = make_signal([SynthEvent(1.0, 0.02, -50)], duration_s=3.0,
                      sample_rate_hz=25_000, noise_sigma_pA=1.0, seed=21)
    res = analyze(_rec(sig.current, sig.sample_rate_hz), PipelineConfig())
    assert res.descs is None


def test_analyze_can_skip_descriptions():
    """The GUI computes descriptions lazily, so analyze() must support skipping."""
    from nanopore.analyze import analyze
    from nanopore.config import PipelineConfig

    sig = make_signal([SynthEvent(1.0, 0.02, -50)], duration_s=3.0,
                      sample_rate_hz=25_000, noise_sigma_pA=1.0, seed=21)
    cfg = PipelineConfig(enabled_mods=("describe",))
    res = analyze(_rec(sig.current, sig.sample_rate_hz), cfg,
                  with_descriptions=False)
    assert res.descs is None
