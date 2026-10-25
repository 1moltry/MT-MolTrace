"""Shared detector catalog and config normalization contracts."""

from __future__ import annotations

from dataclasses import asdict, fields

import pytest

from nanopore.config import PipelineConfig
from nanopore.params import ParamSpec
from nanopore.registry import (DETECTOR_ORDER, DETECTORS, get_detector,
                               list_detectors, normalize_config,
                               resolve_detector_id)


def test_detector_registry_integrity():
    assert tuple(DETECTOR_ORDER) == tuple(DETECTORS)
    assert len(DETECTOR_ORDER) == len(set(DETECTOR_ORDER))
    assert len({spec.label for spec in DETECTORS.values()}) == len(DETECTORS)
    valid = {f.name for f in fields(PipelineConfig)}
    for det_id in DETECTOR_ORDER:
        spec = get_detector(det_id)
        assert spec.id == det_id
        assert spec.label and spec.desc
        for name in spec.params:
            assert name in valid, f"{det_id} references unknown config field {name}"


def test_detector_registry_order_is_stable():
    assert [spec.id for spec in list_detectors()] == ["level", "burst", "plateau"]


def test_resolve_detector_prefers_explicit_id():
    assert resolve_detector_id(PipelineConfig(detector="plateau")) == "plateau"


def test_resolve_detector_legacy_event_mode():
    assert resolve_detector_id(PipelineConfig(event_mode="burst")) == "burst"
    assert resolve_detector_id(PipelineConfig()) == "level"


def test_unknown_detector_warns_and_falls_back():
    cfg = PipelineConfig(detector="future_method", event_mode="burst")
    with pytest.warns(UserWarning, match="unknown detector"):
        assert resolve_detector_id(cfg) == "burst"


def test_normalize_config_canonicalizes_detector_and_mods():
    cfg = PipelineConfig(detector="plateau", event_mode="burst",
                         enabled_mods=("refined_anomaly",))
    out = normalize_config(cfg)
    assert out.detector == "plateau"
    assert out.event_mode == "level"
    assert out.enabled_mods == ("dynamic_i0", "anomaly", "refined_anomaly")
    # normalization returns a copy; the caller's protocol is not mutated
    assert cfg.event_mode == "burst"


def test_config_all_fields_json_roundtrip(tmp_path):
    cfg = PipelineConfig(
        hist_bins=321, update_levels="all", dwell_min_frac=0.42,
        plateau_min_dwell_ms=12.5, plateau_dwell_max_ms=345.0,
        plateau_voltage_tol_mv=7.5, plateau_cutoff_hz=1234.0,
        jump_min_ms=77.0, refined_jitter_window_ms=123.0,
        refined_rupture_iqr_min_pA=91.0, refined_drift_min_s=44.0,
        enabled_mods=("plots",), label="roundtrip",
    )
    path = tmp_path / "protocol.json"
    cfg.save(path)
    loaded = PipelineConfig.load(path)
    assert asdict(loaded) == asdict(cfg)


def test_param_spec_is_qt_free_metadata():
    p = ParamSpec("k_max", 30, "int", "最大段数", "DP 上限", minimum=1, maximum=200)
    assert p.name == "k_max" and p.default == 30 and p.maximum == 200
