"""Fingerprint contracts: event identity, cache key, schema 1.1, registry."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from nanopore.io import AbfRecording
from tests.synth import SynthEvent, make_signal


def _rec(current: np.ndarray, fs: float = 25_000.0, path: str = "synthetic.abf",
         voltage=None) -> AbfRecording:
    return AbfRecording(path=Path(path), current=current, sample_rate_hz=fs,
                        units="pA", n_channels=1, sweep_count=1, voltage=voltage)


def _two_events(seed: int = 7):
    sig = make_signal([SynthEvent(0.5, 0.02, -50.0),
                       SynthEvent(1.0, 0.10, -50.0)],
                      duration_s=3.0, sample_rate_hz=25_000.0,
                      noise_sigma_pA=1.0, seed=seed)
    return sig


def test_source_id_is_content_addressed(tmp_path):
    from nanopore.fingerprint import source_id_for_path

    a = tmp_path / "a.abf"
    b = tmp_path / "b.abf"
    a.write_bytes(b"same-bytes")
    b.write_bytes(b"same-bytes")
    c = tmp_path / "c.abf"
    c.write_bytes(b"other-bytes")

    assert source_id_for_path(a).startswith("sha256:")
    assert source_id_for_path(a) == source_id_for_path(b)
    assert source_id_for_path(a) != source_id_for_path(c)


def test_source_id_fallback_is_stable_and_distinct():
    from nanopore.fingerprint import fallback_source_id

    x = np.zeros(1000)
    y = np.zeros(1000)
    y[0] = 1.0
    assert fallback_source_id("missing.abf", x) == fallback_source_id("missing.abf", x)
    assert fallback_source_id("missing.abf", x) != fallback_source_id("missing.abf", y)


def test_event_key_ignores_row_number_and_export_thresholds():
    """The same physical event keeps its key when an earlier event is filtered."""
    from nanopore.analyze import analyze
    from nanopore.config import PipelineConfig

    sig = _two_events()
    rec = _rec(sig.current)
    keep_all = analyze(rec, PipelineConfig(enabled_mods=("describe",),
                                           min_toff_ms=0.0))
    drop_short = analyze(rec, PipelineConfig(enabled_mods=("describe",),
                                             min_toff_ms=50.0))
    assert len(keep_all.df) == 2
    assert len(drop_short.df) == 1

    long_event = keep_all.descs[1]
    survivor = drop_short.descs[0]
    assert long_event.legacy_event_id == 2
    assert survivor.legacy_event_id == 1
    assert long_event.event_key == survivor.event_key
    assert long_event.source_id == survivor.source_id


def test_event_key_uses_boundary_and_rate():
    from nanopore.fingerprint import event_key

    base = event_key("sha256:abc", 25_000.0, 100, 200)
    assert base == event_key("sha256:abc", 25_000.0, 100, 200)
    assert base != event_key("sha256:abc", 50_000.0, 100, 200)
    assert base != event_key("sha256:abc", 25_000.0, 101, 200)
    assert base != event_key("sha256:def", 25_000.0, 100, 200)
    assert len(base) == 16


def test_cache_key_tracks_params_and_data():
    from nanopore.analyze import analyze
    from nanopore.config import PipelineConfig
    from nanopore.fingerprint import cache_key, get_describer, view_for

    sig = _two_events()
    res = analyze(_rec(sig.current), PipelineConfig(enabled_mods=("describe",)))
    describer = get_describer("dp_bic")
    view = view_for(res, 0, describer)

    k1 = cache_key(view, describer, {"k_max": 30})
    assert k1 == cache_key(view, describer, {"k_max": 30})
    assert k1 != cache_key(view, describer, {"k_max": 20})
    assert k1 != cache_key(view, describer, {"k_max": 30, "snr_min": 1.0})

    other = view_for(res, 1, describer)
    assert cache_key(other, describer, {"k_max": 30}) != k1
    assert k1[0] == view.event_key and k1[1] == "dp_bic" and k1[2] == describer.version


def test_description_json_keeps_old_keys():
    from nanopore.analyze import analyze
    from nanopore.config import PipelineConfig
    from nanopore.fingerprint import descriptions_to_json, to_json

    sig = _two_events()
    res = analyze(_rec(sig.current), PipelineConfig(enabled_mods=("describe",)))
    desc = res.descs[0]
    payload = to_json(desc)
    assert set(payload) >= {"event_id", "source", "describer", "describer_version",
                            "schema_version", "params", "features", "quality",
                            "payload", "segments"}
    assert payload["schema_version"] == "1.1"
    assert payload["event_key"] == desc.event_key
    assert payload["segments"][0]["start_global"] == desc.event_start + desc.segments[0].start

    doc = descriptions_to_json(res.descs, "synthetic.abf")
    assert doc["schema_version"] == "1.1"
    assert set(doc) >= {"source", "describer", "describer_version", "params", "events"}
    assert doc["source_id"] == desc.source_id
    assert doc["manifest"]["source_id"] == desc.source_id
    assert doc["manifest"]["detector_id"] == "level"


def test_registry_metadata():
    from nanopore.fingerprint import (MATURITY_LEVELS, describe_meta,
                                      describer_ids, get_describer)

    assert {"scalar", "dp_bic"} <= set(describer_ids())
    for info in describe_meta():
        assert info["maturity"] in MATURITY_LEVELS
        assert info["input_trace"] in ("analysis", "raw")
        assert info["params"], info["id"]
    assert get_describer("dp_bic").input_trace == "analysis"
    with pytest.raises(KeyError):
        get_describer("not_a_describer")
