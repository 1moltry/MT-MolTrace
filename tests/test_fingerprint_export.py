"""Fingerprint exports: old columns preserved, 1.1 provenance appended, keys match."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.io import loadmat

from nanopore.analysis import (FINGERPRINT_SEGMENT_COLUMNS,
                               FINGERPRINT_SEGMENT_COLUMNS_V11,
                               write_event_waveforms, write_fingerprints)
from nanopore.io import AbfRecording


def _three_step_analysis():
    from nanopore.analyze import AnalysisResult
    from nanopore.config import PipelineConfig
    from nanopore.fingerprint import describe_result

    fs = 50_000.0
    rng = np.random.default_rng(0)
    current = np.full(30_000, 100.0) + rng.normal(0, 1.0, 30_000)
    s, e = 10_000, 12_000
    third = (e - s) // 3
    current[s:s + third] = 60.0
    current[s + third:s + 2 * third] = 20.0
    current[s + 2 * third:e] = 60.0
    rec = AbfRecording(path=Path("synthetic.abf"), current=current,
                       sample_rate_hz=fs, units="pA", n_channels=1,
                       sweep_count=1)
    cfg = PipelineConfig(enabled_mods=("describe",))
    df = pd.DataFrame([{"t1": s / fs, "t2": e / fs, "Io": 100.0,
                        "mean": -40.0, "state": "A"}])
    res = AnalysisResult(rec, None, current, None, None, None, df, None,
                         detector_id="level", enabled_mods=("describe",),
                         config=cfg)
    res.descs = describe_result(res)
    return res


def test_fingerprint_xlsx_appends_1_1_columns(tmp_path):
    res = _three_step_analysis()
    paths = write_fingerprints(res.descs, tmp_path, "demo",
                               fs=res.rec.sample_rate_hz, source="synthetic.abf")
    sheets = pd.read_excel(paths["xlsx"], sheet_name=None)

    seg_cols = list(sheets["segments"].columns)
    assert seg_cols[:len(FINGERPRINT_SEGMENT_COLUMNS)] == FINGERPRINT_SEGMENT_COLUMNS
    assert seg_cols[len(FINGERPRINT_SEGMENT_COLUMNS):] == FINGERPRINT_SEGMENT_COLUMNS_V11

    ev_cols = list(sheets["events"].columns)
    assert ev_cols[:4] == ["event_id", "describer", "valid", "reason"]
    for name in ("event_key", "source_id", "legacy_event_id",
                 "event_start_sample", "event_end_sample", "params_hash",
                 "trace_source", "coverage_frac"):
        assert name in ev_cols

    desc = res.descs[0]
    seg = sheets["segments"]
    event_start = int(sheets["events"]["event_start_sample"].iloc[0])
    assert event_start == desc.event_start
    assert (seg["event_key"] == desc.event_key).all()
    assert (seg["start_global"] == event_start + seg["start_sample"]).all()
    assert (seg["end_global"] == event_start + seg["end_sample"]).all()
    assert sheets["events"]["event_key"].iloc[0] == desc.event_key


def test_json_and_xlsx_share_the_event_key(tmp_path):
    res = _three_step_analysis()
    paths = write_fingerprints(res.descs, tmp_path, "demo",
                               fs=res.rec.sample_rate_hz, source="synthetic.abf")
    payload = json.loads(paths["json"].read_text(encoding="utf-8"))
    desc = res.descs[0]

    assert payload["schema_version"] == "1.1"
    assert payload["source_id"] == desc.source_id
    assert payload["manifest"]["params_hash"] == desc.params_hash
    assert payload["manifest"]["source_name"] == "synthetic.abf"
    event = payload["events"][0]
    assert event["event_key"] == desc.event_key
    assert event["event_start"] == desc.event_start
    assert event["coverage"]["coverage_frac"] == desc.coverage["coverage_frac"]

    sheets = pd.read_excel(paths["xlsx"], sheet_name="events")
    assert sheets["event_key"].iloc[0] == event["event_key"]


def test_empty_export_still_carries_the_source_id(tmp_path):
    paths = write_fingerprints([], tmp_path, "empty", fs=25_000.0,
                               source="empty.abf", source_id="sha256:abc")
    payload = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.1"
    assert payload["events"] == []
    assert payload["source_id"] == "sha256:abc"
    assert payload["manifest"]["source_id"] == "sha256:abc"
    assert payload["manifest"]["fs_hz"] == 25_000.0


def test_waveform_export_carries_the_same_key(tmp_path):
    res = _three_step_analysis()
    source_id = res.descs[0].source_id
    mat_path = tmp_path / "demo_events.mat"
    write_event_waveforms(res.df, res.rec.current, res.rec.sample_rate_hz,
                          mat_path, label="demo", source_file="synthetic.abf",
                          units="pA", source_id=source_id)
    data = loadmat(mat_path, simplify_cells=True)

    assert data["source_id"] == source_id
    events = data["events"]
    # a single 1x1 cell simplifies to the struct itself
    ev = events[0] if isinstance(events, (list, tuple, np.ndarray)) else events
    assert ev["event_key"] == res.descs[0].event_key
    assert ev["start_sample"] == int(round(float(res.df["t1"].iloc[0])
                                          * res.rec.sample_rate_hz))


def test_waveform_export_without_source_id_stays_compatible(tmp_path):
    res = _three_step_analysis()
    mat_path = tmp_path / "demo_events.mat"
    write_event_waveforms(res.df, res.rec.current, res.rec.sample_rate_hz, mat_path)
    data = loadmat(mat_path, simplify_cells=True)
    assert np.asarray(data["source_id"]).size == 0     # empty char array
    events = data["events"]
    ev = events[0] if isinstance(events, (list, tuple, np.ndarray)) else events
    assert np.asarray(ev["event_key"]).size == 0
