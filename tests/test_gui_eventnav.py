"""GUI event navigation (offscreen): pan-without-zoom focus, click-to-select,
the zoom slice, and the excluded-events table."""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("PyQt5")
pytest.importorskip("pyqtgraph")

from PyQt5.QtCore import Qt

from nanopore.gui.bus import bus
from nanopore.gui.eventtable import EventTable
from nanopore.gui.excludedview import ExcludedView
from nanopore.gui.sliceview import SliceView
from nanopore.gui.waveview import WaveView


@pytest.fixture(scope="session")
def qapp():
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    return app


class _Rec:
    def __init__(self, current, sr):
        self.current = current
        self.sample_rate_hz = sr


def _df():
    return pd.DataFrame({
        "t1": [1.0, 3.0],
        "t2": [1.5, 3.2],
        "toff": [500.0, 200.0],       # ms
        "mean": [-40.0, -30.0],
        "Io": [100.0, 100.0],
        "state": ["A", "B"],
    })


def _rec():
    sr = 25_000.0
    cur = np.full(int(6.0 * sr), 100.0)
    for a, b in ((1.0, 1.5), (3.0, 3.2)):
        cur[int(a * sr):int(b * sr)] = 60.0
    return _Rec(cur, sr)


# ---- main-view focus: pan, don't zoom ------------------------------------
def test_focus_event_pans_without_changing_zoom(qapp):
    w = WaveView()
    w.set_data(_rec(), None, _df(), None)
    (x0, x1), (y0, y1) = w.plot.getViewBox().viewRange()
    w.focus_event(3.0, 3.2)                                  # default zoom=False
    (nx0, nx1), (ny0, ny1) = w.plot.getViewBox().viewRange()
    assert (nx1 - nx0) == pytest.approx(x1 - x0, rel=1e-6)   # x span unchanged
    assert (ny1 - ny0) == pytest.approx(y1 - y0, rel=1e-6)   # y untouched
    assert nx0 <= 3.0 <= nx1 and nx0 <= 3.2 <= nx1           # event now visible


def test_focus_event_zoom_true_narrows_span(qapp):
    w = WaveView()
    w.set_data(_rec(), None, _df(), None)
    (x0, x1), _ = w.plot.getViewBox().viewRange()
    w.focus_event(3.0, 3.2, zoom=True)
    (nx0, nx1), _ = w.plot.getViewBox().viewRange()
    assert (nx1 - nx0) < (x1 - x0)


def test_wave_click_selects_nearest_event(qapp):
    w = WaveView()
    w.set_data(_rec(), None, _df(), None)
    got = []

    def _spy(i):
        got.append(i)

    bus.event_selected.connect(_spy)
    try:
        w._click_select(3.1)     # inside event #1
        w._click_select(1.05)    # inside event #0
    finally:
        bus.event_selected.disconnect(_spy)
    assert got == [1, 0]


def _event_df():
    cols = ["t1", "t2", "toff", "mean", "%mean", "Io", "std", "skew", "kurt",
            "MAD", "CV", "q1", "q2", "q3", "iqr", "outlier_ratio", "ton", "state"]
    d = {c: [0.0, 0.0] for c in cols}
    d["t1"] = [1.0, 3.0]
    d["t2"] = [1.5, 3.2]
    d["state"] = ["A", "B"]
    return pd.DataFrame(d)


# ---- event table: stable 序号 -------------------------------------------
def test_event_table_has_stable_row_numbers(qapp):
    table = EventTable()
    table.set_data(_event_df())
    m = table.model
    assert m.headerData(0, Qt.Horizontal) == "序号"
    assert m.data(m.index(0, 0)) == "1"
    assert m.data(m.index(1, 0)) == "2"
    # filtering by state keeps the original (stable) numbering
    table.state_combo.setCurrentText("B")
    assert m.rowCount() == 1
    assert m.data(m.index(0, 0)) == "2"


# ---- zoom slice ----------------------------------------------------------
def test_slice_shows_event(qapp):
    view = SliceView()
    view.set_row(_df().iloc[0], _rec().current, 25_000.0)
    xs, _ = view.curve.getData()
    assert xs is not None and len(xs) > 0
    assert "dwell 500.000 ms" in view._title.text()
    assert len(view._markers) >= 2          # start/end lines (+ open-pore ref)


def test_slice_title_shows_event_number(qapp):
    view = SliceView()
    view.set_row(_df().iloc[0], _rec().current, 25_000.0, number=7)
    assert "事件 #7" in view._title.text()


def test_slice_clear(qapp):
    view = SliceView()
    view.set_row(_df().iloc[0], _rec().current, 25_000.0)
    view.clear()
    xs, _ = view.curve.getData()
    assert xs is None or len(xs) == 0


# ---- excluded-events table ----------------------------------------------
def test_excluded_view_lists_and_signals(qapp):
    picks = []
    view = ExcludedView(on_select=lambda row, n: picks.append((row, n)))
    df_ex = pd.DataFrame({
        "t1": [2.0], "t2": [2.1], "toff": [100.0], "mean": [-9.0],
        "Io": [100.0], "state": ["A"], "drop_reason": ["toff<min"],
    })
    view.set_data(df_ex)
    assert view.model.rowCount() == 1
    assert "剔除事件 1" in view.summary.text()
    assert view.model.data(view.model.index(0, 0)) == "1"      # 序号
    view.view.selectRow(0)
    assert len(picks) == 1
    assert picks[0][1] == 1                                    # 1-based number
    assert float(picks[0][0]["t1"]) == 2.0
