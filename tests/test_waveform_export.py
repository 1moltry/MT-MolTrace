"""waveform_export mod: per-event raw current sequences in a MATLAB .mat file."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy.io import loadmat

from nanopore.analysis import write_event_waveforms
from nanopore.config import PipelineConfig
from tests.synth import SynthEvent, make_signal


def _load(path: Path) -> dict:
    return loadmat(path, simplify_cells=True)


def _events(data: dict) -> list:
    """Event list from a loaded file. scipy's simplify_cells collapses a
    single-element cell to a bare dict, so normalise that back to a list."""
    ev = data["events"]
    if isinstance(ev, dict):
        return [ev]
    if isinstance(ev, np.ndarray):
        ev = ev.ravel().tolist()
    return list(ev)


def _df(t1s, t2s) -> pd.DataFrame:
    return pd.DataFrame({"t1": np.asarray(t1s, float), "t2": np.asarray(t2s, float)})


# ---------------- exact sample slice, no margin ----------------
def test_waveform_is_exact_event_slice(tmp_path):
    sig = make_signal([SynthEvent(1.0, 0.5, -50.0)], duration_s=3.0, seed=1)
    sr = sig.sample_rate_hz
    out = tmp_path / "x_events.mat"
    write_event_waveforms(_df([1.0], [1.5]), sig.current, sr, out,
                          label="L", source_file="x.abf")

    ev = _events(_load(out))[0]
    s, e = int(round(1.0 * sr)), int(round(1.5 * sr))
    assert np.array_equal(ev["current_pA"].ravel(), sig.current[s:e])
    assert ev["start_sample"] == s
    assert ev["n_samples"] == e - s
    assert ev["t1_s"] == pytest.approx(1.0)
    assert ev["t2_s"] == pytest.approx(1.5)
    assert ev["fs_hz"] == pytest.approx(sr)
    assert ev["event_id"] == 1


def test_multiple_events_keep_kept_row_order(tmp_path):
    sig = make_signal([SynthEvent(0.5, 0.2, -40.0), SynthEvent(1.5, 0.3, -60.0)],
                      duration_s=3.0, seed=2)
    sr = sig.sample_rate_hz
    out = tmp_path / "x_events.mat"
    write_event_waveforms(_df([1.5, 0.5], [1.8, 0.7]), sig.current, sr, out)

    events = _events(_load(out))
    assert [ev["event_id"] for ev in events] == [1, 2]
    # first exported row is the 1.5-1.8 s event, second the 0.5-0.7 s one
    assert events[0]["n_samples"] == int(round(1.8 * sr)) - int(round(1.5 * sr))
    assert events[1]["n_samples"] == int(round(0.7 * sr)) - int(round(0.5 * sr))


def test_slice_clamped_at_record_end(tmp_path):
    sig = make_signal([], duration_s=1.0, seed=3)
    sr = sig.sample_rate_hz
    n = len(sig.current)
    out = tmp_path / "x_events.mat"
    write_event_waveforms(_df([0.9], [5.0]), sig.current, sr, out)   # t2 past EOF

    ev = _events(_load(out))[0]
    assert ev["start_sample"] == int(round(0.9 * sr))
    assert ev["n_samples"] == n - int(round(0.9 * sr))
    assert ev["current_pA"].ravel().size == ev["n_samples"]


def test_degenerate_event_is_skipped(tmp_path):
    sig = make_signal([], duration_s=1.0, seed=4)
    out = tmp_path / "x_events.mat"
    write_event_waveforms(_df([0.5, 0.6], [0.5, 0.7]), sig.current, sig.sample_rate_hz, out)

    events = _events(_load(out))
    assert len(events) == 1
    assert events[0]["t1_s"] == pytest.approx(0.6)


def test_empty_table_still_loads_as_empty_cell(tmp_path):
    sig = make_signal([], duration_s=0.5, seed=5)
    out = tmp_path / "x_events.mat"
    write_event_waveforms(_df([], []), sig.current, sig.sample_rate_hz, out,
                          source_file="empty.abf")

    data = _load(out)
    assert data["source_file"] == "empty.abf"
    assert list(data["events"]) == []


def test_metadata_roundtrip(tmp_path):
    sig = make_signal([], duration_s=0.5, seed=6)
    out = tmp_path / "x_events.mat"
    write_event_waveforms(_df([], []), sig.current, sig.sample_rate_hz, out,
                          label="sym-A", source_file="sym.abf", units="pA")

    data = _load(out)
    assert data["label"] == "sym-A"
    assert data["units"] == "pA"
    assert data["fs_hz"] == pytest.approx(sig.sample_rate_hz)


# ---------------- end-to-end: the pipeline hook uses RAW current ----------------
_SAMPLE = Path("abf数据案例/abf数据案例/Ala.abf")


@pytest.mark.skipif(not _SAMPLE.exists(), reason="local sample data not present")
def test_pipeline_exports_raw_even_with_lowpass(tmp_path):
    """lowpass changes the detected boundaries, but the exported samples must be
    the raw trace, not the filtered one."""
    from nanopore.io import read_abf
    from nanopore.pipeline import process_file

    cfg = PipelineConfig(enabled_mods=("lowpass", "waveform_export"),
                         filter_lowpass_hz=2000.0)
    df, _ = process_file(_SAMPLE, tmp_path, cfg)
    out = tmp_path / "Ala_events.mat"
    assert out.exists()

    raw = read_abf(_SAMPLE).current
    events = _load(out)["events"]
    assert len(events) == len(df)
    for ev in events:
        s, n = ev["start_sample"], ev["n_samples"]
        assert np.array_equal(ev["current_pA"].ravel(), raw[s:s + n])


@pytest.mark.skipif(not _SAMPLE.exists(), reason="local sample data not present")
def test_pipeline_omits_mat_without_mod(tmp_path):
    from nanopore.pipeline import process_file

    process_file(_SAMPLE, tmp_path, PipelineConfig(enabled_mods=()))
    assert not (tmp_path / "Ala_events.mat").exists()
