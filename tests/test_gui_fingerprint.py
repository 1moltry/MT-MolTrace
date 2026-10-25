"""Fingerprint GUI: module toggle, segment table, slice overlay, toolbar sync."""

from __future__ import annotations

import os
import sys

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
    app = QApplication.instance() or QApplication(sys.argv)
    return app


def _event_and_desc():
    from nanopore.config import PipelineConfig
    from nanopore.describe import describe_rows
    from nanopore.io import AbfRecording

    fs = 50_000.0
    rng = np.random.default_rng(0)
    current = np.full(30_000, 100.0) + rng.normal(0, 1.0, 30_000)
    s, e = 10_000, 12_000
    third = (e - s) // 3
    current[s:s + third] = 60.0
    current[s + third:s + 2 * third] = 20.0
    current[s + 2 * third:e] = 60.0
    rec = AbfRecording(path=__import__("pathlib").Path("synthetic.abf"),
                       current=current, sample_rate_hz=fs, units="pA",
                       n_channels=1, sweep_count=1)
    row = pd.Series({"t1": s / fs, "t2": e / fs, "Io": 100.0,
                     "toff": (e - s) / fs * 1000.0, "mean": -40.0, "state": "A"})
    desc = describe_rows(pd.DataFrame([row]), rec,
                         PipelineConfig(enabled_mods=("describe",)))[0]
    return rec, row, desc


@pytest.fixture()
def panel(qapp, monkeypatch):
    from nanopore.gui import parampanel as pp

    monkeypatch.setattr(pp, "_SETTINGS", ("MOLTRACE-test-fp", "gui"))
    QSettings("MOLTRACE-test-fp", "gui").clear()
    p = pp.ParamPanel()
    yield p
    p.deleteLater()


def test_describe_toggle_updates_config(panel):
    panel.set_mod_enabled("describe", True)
    assert "describe" in panel.enabled_ids()
    cfg = panel.build_config()
    assert cfg.describer == "dp_bic"
    assert cfg.describe_params["k_max"] == 30
    assert cfg.describe_params["snr_min"] == 0.0

    panel.set_mod_enabled("describe", False)
    assert "describe" not in panel.enabled_ids()


def test_segment_table_fills_rows(qapp):
    from nanopore.gui.segmenttable import SegmentTable

    rec, _row, desc = _event_and_desc()
    table = SegmentTable()
    table.set_description(desc, rec.sample_rate_hz)

    assert table.table.rowCount() == 3
    assert not table.table.isHidden()
    assert table.table.item(0, 0).text() == "1"
    assert abs(float(table.table.item(1, 4).text()) - 20.0) < 2.0


def test_slice_draws_segments(qapp):
    from nanopore.gui.sliceview import SliceView

    rec, row, desc = _event_and_desc()
    view = SliceView()
    view.set_row(row, rec.current, rec.sample_rate_hz, number=1, desc=desc)

    assert len(view._seg_levels) == 3
    assert len(view._seg_items) == 4          # 3 starts + final end
    assert "指纹 3 段" in view._title.text()


def test_describe_worker_returns_description(qapp):
    from PyQt5.QtTest import QSignalSpy

    from nanopore.analyze import AnalysisResult
    from nanopore.config import PipelineConfig
    from nanopore.gui.controller import DescribeWorker

    rec, row, _desc = _event_and_desc()
    cfg = PipelineConfig(enabled_mods=("describe",))
    analysis = AnalysisResult(
        rec, None, rec.current, None, None, None,
        pd.DataFrame([row]), None,
        detector_id="level", enabled_mods=("describe",), config=cfg)
    worker = DescribeWorker(analysis, 0, cfg)
    spy = QSignalSpy(worker.done)
    worker.start()
    assert worker.wait(60_000)
    assert len(spy) == 1
    key, desc = spy[0]
    assert isinstance(key, tuple) and key[0] == desc.event_key
    assert desc.event_id == 1
    assert len(desc.segments) == 3


def test_toolbar_toggle_syncs_module(qapp, monkeypatch):
    from nanopore.gui import parampanel as pp

    monkeypatch.setattr(pp, "_SETTINGS", ("MOLTRACE-test-fp-win", "gui"))
    QSettings("MOLTRACE-test-fp-win", "gui").clear()

    from nanopore.gui.main_window import MainWindow

    win = MainWindow()
    try:
        assert not win.act_fp.isChecked()
        win.act_fp.setChecked(True)
        assert "describe" in win.params.enabled_ids()
        assert win.act_fp.isChecked()
        win.act_fp.setChecked(False)
        assert "describe" not in win.params.enabled_ids()
    finally:
        win.close()
        win.deleteLater()
