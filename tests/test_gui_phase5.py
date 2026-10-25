"""Phase 5 GUI: registry-driven parameters, side-by-side segments, export.

Runs offscreen; no local .abf data required.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("PyQt5")
pytest.importorskip("pyqtgraph")

from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


def _analysis():
    from nanopore.analyze import AnalysisResult
    from nanopore.config import PipelineConfig
    from nanopore.io import AbfRecording

    fs = 50_000.0
    rng = np.random.default_rng(0)
    current = np.full(30_000, 100.0) + rng.normal(0.0, 1.0, 30_000)
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
    analysis = AnalysisResult(rec, None, current, None, None, None, df, None,
                              detector_id="level", enabled_mods=("describe",),
                              config=cfg)
    return analysis, rec, cfg


@pytest.fixture()
def panel(qapp, monkeypatch):
    from nanopore.gui import parampanel as pp

    monkeypatch.setattr(pp, "_SETTINGS", ("MOLTRACE-test-p5", "gui"))
    QSettings("MOLTRACE-test-p5", "gui").clear()
    p = pp.ParamPanel()
    yield p
    p.deleteLater()


def test_param_panel_is_generated_from_the_registry(panel):
    from nanopore.fingerprint import describe_meta, get_describer

    ids = [panel.describer.itemData(i) for i in range(panel.describer.count())]
    assert set(ids) == {info["id"] for info in describe_meta()}

    dp = get_describer("dp_bic")
    assert set(panel._fp_widgets) == {p.name for p in dp.params}
    cfg = panel.build_config()
    assert cfg.describer == "dp_bic"
    assert cfg.describe_params["k_max"] == 30
    assert cfg.describe_params["snr_min"] == 0.0


def test_switching_describer_rebuilds_its_parameters(panel):
    panel.set_mod_enabled("describe", True)
    panel.set_describer("classic", notify=False)

    assert panel.current_describer() == "classic"
    assert "thresh_sigma" in panel._fp_widgets
    assert "k_max" not in panel._fp_widgets
    cfg = panel.build_config()
    assert cfg.describer == "classic"
    assert cfg.describe_params["thresh_sigma"] == 10.0
    assert "测试" in panel.fp_maturity.text()


def test_segment_table_compares_two_describers(qapp):
    from nanopore.fingerprint import describe_result
    from nanopore.gui.segmenttable import SegmentTable

    analysis, rec, cfg = _analysis()
    dp = describe_result(analysis, cfg, describer_id="dp_bic")[0]
    classic = describe_result(analysis, cfg, describer_id="classic")[0]
    table = SegmentTable()
    table.set_description(dp, rec.sample_rate_hz, "dp_bic")
    assert table.table.rowCount() == 3

    table.compare_box.setChecked(True)
    table.set_comparison(classic, rec.sample_rate_hz, "classic")
    assert table.is_comparing()
    assert not table._box_b.isHidden()
    assert table._label_b.text() == "classic"
    assert table.table_b.rowCount() == len(classic.segments)


def test_compare_defaults_to_a_different_describer(qapp):
    from nanopore.gui.segmenttable import SegmentTable

    table = SegmentTable()
    table.set_current_describer("classic")
    table.compare_box.setChecked(True)
    assert table.comparison_describer() != "classic"


def test_controller_invalidates_descriptions_on_config_change(qapp):
    from nanopore.config import PipelineConfig
    from nanopore.gui.controller import Controller

    c = Controller()
    c.desc_cache[("stale",)] = object()
    c._desc_gen = 0
    c.set_config(PipelineConfig(describer="classic"))
    assert c.desc_cache == {}
    assert c._desc_gen == 1


def test_controller_discards_descriptions_from_an_older_generation(qapp):
    from types import SimpleNamespace

    from nanopore.gui.controller import Controller

    c = Controller()
    c._desc_gen = 2
    c._desc_pending.add(("k",))
    c._on_described(("k",), SimpleNamespace(event_id=1, describer="dp_bic"), 1)
    assert c.desc_cache == {}
    assert ("k",) not in c._desc_pending

    c._desc_pending.add(("k2",))
    c._on_desc_failed("boom", ("k2",), 2)
    assert ("k2",) not in c._desc_pending


def test_export_worker_writes_the_same_files_as_batch(qapp, tmp_path):
    from PyQt5.QtTest import QSignalSpy

    from nanopore.gui.controller import ExportDescriptionsWorker

    analysis, rec, cfg = _analysis()
    worker = ExportDescriptionsWorker(analysis, rec, tmp_path, cfg)
    spy = QSignalSpy(worker.done)
    worker.start()
    assert worker.wait(60_000)
    assert len(spy) == 1

    paths = spy[0][0]
    assert Path(paths["xlsx"]).exists() and Path(paths["json"]).exists()
    sheets = pd.read_excel(paths["xlsx"], sheet_name=None)
    assert set(sheets) == {"events", "segments", "params"}
    assert len(sheets["segments"]) == 3


def test_batch_dialog_shows_describer_and_anomaly_state(qapp):
    from nanopore.config import PipelineConfig
    from nanopore.gui.batchdialog import BatchDialog

    dlg = BatchDialog(PipelineConfig(enabled_mods=("describe",)), None)
    try:
        assert "描述器" in dlg.describer_note.text() or "开启" in dlg.describer_note.text()
        assert "异常识别：关" in dlg.anomaly_note.text()
        dlg._cfg = PipelineConfig(enabled_mods=("anomaly", "describe"))
        dlg._refresh_notes()
        assert "异常识别：开" in dlg.anomaly_note.text()
    finally:
        dlg.close()
