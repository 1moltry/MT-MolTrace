"""Feature-module registry, config wiring, and the shared analyze() path."""

import os
from dataclasses import fields
from pathlib import Path

import numpy as np
import pytest

from nanopore.analyze import analyze
from nanopore.config import PipelineConfig
from nanopore.mods import CATEGORIES, MODS, ORDER, all_mods, resolve_mods
from tests.synth import SynthEvent, make_signal


# ---------------- registry ----------------
def test_registry_integrity():
    assert set(ORDER) == set(MODS), "ORDER must cover exactly the registry"
    assert len(set(ORDER)) == len(ORDER), "ORDER has duplicates"
    valid_params = {f.name for f in fields(PipelineConfig)}
    for mid in ORDER:
        spec = MODS[mid]
        assert spec.id == mid
        for dep in spec.requires:
            assert dep in MODS, f"{mid} requires unknown {dep}"
        for p in spec.params:
            assert p in valid_params, f"{mid} references non-config param {p}"


def test_categories_cover_registry():
    ids = [cid for cid, _ in CATEGORIES]
    assert len(ids) == len(set(ids))
    known = dict(CATEGORIES)
    for mid in ORDER:
        assert MODS[mid].category in known, f"{mid} has unknown category"
    for cid in ids:
        assert any(MODS[mid].category == cid for mid in ORDER), f"{cid} is empty"


def test_resolve_adds_dependencies_in_order():
    assert resolve_mods(["refined_anomaly"]) == ("dynamic_i0", "anomaly", "refined_anomaly")


def test_resolve_dedupes_and_orders():
    assert resolve_mods(["plots", "lowpass", "plots"]) == ("lowpass", "plots")


def test_resolve_ignores_unknown():
    with pytest.warns(UserWarning):
        assert resolve_mods(["nope", "plots"]) == ("plots",)


def test_resolve_empty():
    assert resolve_mods(()) == ()
    assert resolve_mods(None) == ()


# ---------------- config ----------------
def test_config_mods_default_empty_and_legacy_flags_gone():
    cfg = PipelineConfig()
    assert cfg.enabled_mods == ()
    for dead in ("anomaly_enabled", "dynamic_i0_enabled", "refined_anomaly_enabled"):
        assert not hasattr(cfg, dead)


def test_config_mods_json_roundtrip(tmp_path):
    cfg = PipelineConfig(enabled_mods=("dynamic_i0", "plots"))
    p = tmp_path / "params.json"
    cfg.save(p)
    loaded = PipelineConfig.load(p)
    assert tuple(loaded.enabled_mods) == ("dynamic_i0", "plots")


def test_config_load_legacy_json_with_dead_flags(tmp_path):
    # an old protocol carrying the removed *_enabled fields must still load
    p = tmp_path / "old.json"
    p.write_text('{"anomaly_enabled": true, "dynamic_i0_enabled": true, '
                 '"ignore_duration_ms": 3.0}', encoding="utf-8")
    cfg = PipelineConfig.load(p)
    assert cfg.ignore_duration_ms == 3.0
    assert cfg.enabled_mods == ()          # dead flags dropped, base-only


# ---------------- analyze() orchestration ----------------
def _fake_rec(sig):
    return type("R", (), {
        "current": sig.current,
        "sample_rate_hz": sig.sample_rate_hz,
        "path": Path("synth_0000.abf"),
        "protocol_voltage": None,
    })()


def _signal():
    events = [SynthEvent(start_s=1.0, duration_s=0.5, amplitude_pA=-50.0),
              SynthEvent(start_s=3.0, duration_s=0.4, amplitude_pA=-50.0)]
    return make_signal(events, duration_s=6.0, seed=1)


def test_analyze_base_only_has_no_mod_artifacts():
    rec = _fake_rec(_signal())
    res = analyze(rec, PipelineConfig(level0=100.0, level1=50.0))
    assert res.anom is None
    assert res.i0_profile is None
    assert res.df_excluded is None or len(res.df_excluded) == 0
    assert len(res.df) == 2


def test_analyze_dynamic_i0_mod():
    rec = _fake_rec(_signal())
    res = analyze(rec, PipelineConfig(level0=100.0, level1=50.0,
                                      enabled_mods=("dynamic_i0",)))
    assert res.i0_profile is not None
    assert res.anom is None


def test_analyze_anomaly_mod():
    rec = _fake_rec(_signal())
    res = analyze(rec, PipelineConfig(level0=100.0, level1=50.0,
                                      enabled_mods=("anomaly",)))
    assert res.anom is not None


def test_analyze_refined_pulls_prerequisites():
    rec = _fake_rec(_signal())
    cfg = PipelineConfig(level0=100.0, level1=50.0,
                         enabled_mods=resolve_mods(("refined_anomaly",)))
    res = analyze(rec, cfg)
    assert res.anom is not None
    assert res.i0_profile is not None       # dependency auto-enabled


# ---------------- end-to-end batch (needs a local .abf) ----------------
_SAMPLE = Path("abf数据案例/abf数据案例/Ala.abf")


@pytest.mark.skipif(not _SAMPLE.exists(), reason="local sample data not present")
def test_run_batch_minimal_writes_only_events_table(tmp_path):
    from nanopore.pipeline import run_batch

    run_batch([_SAMPLE], tmp_path, PipelineConfig(enabled_mods=()))
    names = {p.name for p in tmp_path.iterdir()}
    assert "Ala_events.xlsx" in names
    assert "Ala_events.mat" not in names
    assert "dataset_all.csv" not in names
    assert "summary.xlsx" not in names
    assert not any(n.endswith("_overview.png") for n in names)


@pytest.mark.skipif(not _SAMPLE.exists(), reason="local sample data not present")
def test_run_batch_all_writes_every_output(tmp_path):
    from nanopore.pipeline import run_batch

    run_batch([_SAMPLE], tmp_path, PipelineConfig(enabled_mods=all_mods()))
    names = {p.name for p in tmp_path.iterdir()}
    assert "Ala_events.xlsx" in names
    assert "Ala_overview.png" in names
    assert "Ala_scatter.png" in names
    assert "Ala_hist.png" in names
    assert "Ala_events.mat" in names
    assert "dataset_all.csv" in names
    assert "summary.xlsx" in names


# ---------------- GUI param panel (offscreen) ----------------
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_QAPP = None   # keep the QApplication alive (GC of it crashes Qt)


def _panel(monkeypatch):
    global _QAPP
    pytest.importorskip("PyQt5")
    import sys

    from PyQt5.QtCore import QSettings
    from PyQt5.QtWidgets import QApplication

    from nanopore.gui import parampanel as pp

    _QAPP = QApplication.instance() or QApplication(sys.argv)
    # isolate from the user's real persisted selection, and start deterministic
    monkeypatch.setattr(pp, "_SETTINGS", ("MOLTRACE-test", "gui"))
    QSettings("MOLTRACE-test", "gui").clear()
    return pp.ParamPanel()


def test_gui_defaults_to_base_only(monkeypatch):
    panel = _panel(monkeypatch)
    assert panel.enabled_ids() == ()
    assert panel.lowpass_box.isHidden()


def test_gui_enabling_mod_shows_params_and_pulls_deps(monkeypatch):
    panel = _panel(monkeypatch)
    panel.mod_boxes["refined_anomaly"].setChecked(True)
    assert panel.enabled_ids() == ("dynamic_i0", "anomaly", "refined_anomaly")
    assert not panel.i0_box.isHidden()
    assert not panel.refined_box.isHidden()


def test_gui_disabling_prereq_drops_dependent(monkeypatch):
    panel = _panel(monkeypatch)
    panel._set_mods(["refined_anomaly"])           # auto-checks anomaly + dynamic_i0
    panel.mod_boxes["anomaly"].setChecked(False)   # fires _sync_mods
    # refined_anomaly (its dependent) is dropped; dynamic_i0 is independent, stays
    assert panel.enabled_ids() == ("dynamic_i0",)


def test_gui_build_config_carries_enabled_mods(monkeypatch):
    panel = _panel(monkeypatch)
    panel._set_mods(["plots"])
    cfg = panel.build_config()
    assert tuple(cfg.enabled_mods) == ("plots",)
    assert not hasattr(cfg, "anomaly_enabled")


def test_gui_remembers_detection_mode_and_params(monkeypatch):
    panel = _panel(monkeypatch)
    panel.event_mode.setCurrentIndex(panel.event_mode.findData("burst"))
    panel.b_gap.setValue(123.0)
    panel._save_settings()

    from nanopore.gui import parampanel as pp

    restored = pp.ParamPanel()          # same (monkeypatched) QSettings
    assert restored.event_mode.currentData() == "burst"
    assert restored.b_gap.value() == 123.0


def test_gui_burst_open_rule_roundtrip(monkeypatch):
    panel = _panel(monkeypatch)
    panel.b_open.setValue(0.80)
    panel.b_merge.setValue(150.0)
    cfg = panel.build_config()
    assert cfg.burst_open_cover == 0.80
    assert cfg.burst_merge_max_ms == 150.0
    panel._save_settings()

    from nanopore.gui import parampanel as pp

    restored = pp.ParamPanel()
    assert restored.b_open.value() == 0.80
    assert restored.b_merge.value() == 150.0


def test_gui_emits_changed_on_option_edit(monkeypatch):
    panel = _panel(monkeypatch)
    got = []
    panel.changed.connect(lambda: got.append(1))
    panel.b_gap.setValue(77.0)                    # spin box edit
    panel.event_mode.setCurrentIndex(panel.event_mode.findData("burst"))
    panel.mod_boxes["plots"].setChecked(True)     # module toggle
    assert len(got) >= 3


def test_gui_modules_are_grouped_into_tabs(monkeypatch):
    from PyQt5.QtWidgets import QCheckBox

    panel = _panel(monkeypatch)
    assert panel.mod_tabs.count() == len(CATEGORIES)
    boxes = []
    for i in range(panel.mod_tabs.count()):
        boxes.extend(panel.mod_tabs.widget(i).findChildren(QCheckBox))
    assert set(boxes) == set(panel.mod_boxes.values())
    assert len(boxes) == len(ORDER)


def test_gui_tab_switch_keeps_selection(monkeypatch):
    panel = _panel(monkeypatch)
    panel._set_mods(["refined_anomaly"])
    before = panel.enabled_ids()
    for i in range(panel.mod_tabs.count()):
        panel.mod_tabs.setCurrentIndex(i)
        assert panel.enabled_ids() == before


def test_gui_dependency_from_non_current_tab(monkeypatch):
    panel = _panel(monkeypatch)
    panel.mod_tabs.setCurrentIndex(0)             # refined_anomaly lives elsewhere
    panel.mod_boxes["refined_anomaly"].setChecked(True)
    assert panel.enabled_ids() == ("dynamic_i0", "anomaly", "refined_anomaly")


def test_gui_module_summary_counts_all_tabs(monkeypatch):
    panel = _panel(monkeypatch)
    assert "已选 0" in panel.modbox.title()
    panel._set_mods(["anomaly", "plots"])
    assert "已选 2" in panel.modbox.title()
