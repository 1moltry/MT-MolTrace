"""Selected-event zoom slice (the "事件放大图").

Shows the raw current of the selected event with half-dwell context on each
side, on an event-relative time axis (ms), with markers for the event start/end
and the open-pore reference. Driven by a row of the feature table, so both the
kept-events table and the excluded table can feed it.
"""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget

from .units import SEC_PER_UNIT, TimeAxis

CURVE_COLOR = "#222222"
START_COLOR = (31, 79, 181)
END_COLOR = (214, 39, 40)
REF_COLOR = (44, 160, 44)


def _num(row, key) -> float:
    try:
        return float(row[key])
    except Exception:                                   # noqa: BLE001
        return float("nan")


class SliceView(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._tax = TimeAxis(orientation="bottom")
        self.plot = pg.PlotWidget(axisItems={"bottom": self._tax})
        self.plot.setBackground("w")
        self.plot.showGrid(x=True, y=True, alpha=0.15)
        self.plot.setLabel("bottom", "事件内时间", units="ms")
        self.plot.setLabel("left", "电流", units="pA")
        for ax in ("bottom", "left"):
            a = self.plot.getAxis(ax)
            a.setPen(pg.mkPen("k"))
            a.setTextPen(pg.mkPen("k"))
        self._tax.set_time_unit(SEC_PER_UNIT["ms"])

        self.curve = pg.PlotDataItem(pen=pg.mkPen(CURVE_COLOR, width=1.0))
        self.curve.setClipToView(True)
        # long events can be millions of samples: peak downsampling keeps a
        # short internal plateau from being averaged away
        self.curve.setDownsampling(auto=True, method="peak")
        self.plot.addItem(self.curve)

        self._markers: list = []
        self._title = QLabel("（未选择事件）")
        self._title.setWordWrap(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 0)
        lay.addWidget(self._title)
        lay.addWidget(self.plot)

    # ---- public ----------------------------------------------------------
    def clear(self) -> None:
        self.curve.setData([], [])
        self._clear_markers()
        self._title.setText("（未选择事件）")

    def set_row(self, row, raw, sr) -> None:
        """Draw the event in ``row`` (a feature-table row) from ``raw``/``sr``."""
        if row is None or raw is None or not sr:
            self.clear()
            return
        t1, t2 = _num(row, "t1"), _num(row, "t2")
        if not (np.isfinite(t1) and np.isfinite(t2)) or t2 < t1:
            self.clear()
            return
        span = t2 - t1
        pad = min(max(0.5 * span, 0.005), 0.5)      # half-dwell, clamped to [5ms, 0.5s]
        n = len(raw)
        i0 = max(0, int((t1 - pad) * sr))
        i1 = min(n, int((t2 + pad) * sr) + 1)
        if i1 <= i0:
            self.clear()
            return
        seg = raw[i0:i1]
        t_rel = np.arange(i0, i1) / sr - t1          # seconds, event start at 0
        self.curve.setData(t_rel, seg)
        self._clear_markers()

        for xv, col in ((0.0, START_COLOR), (span, END_COLOR)):
            line = pg.InfiniteLine(pos=xv, angle=90,
                                   pen=pg.mkPen(col, width=1.2, style=Qt.DashLine))
            line.setZValue(5)
            self.plot.addItem(line)
            self._markers.append(line)
        io = _num(row, "Io")
        if np.isfinite(io):
            ref = pg.InfiniteLine(pos=io, angle=0,
                                  pen=pg.mkPen(REF_COLOR, width=1.0, style=Qt.DotLine))
            ref.setZValue(5)
            self.plot.addItem(ref)
            self._markers.append(ref)

        lo, hi = float(np.nanmin(seg)), float(np.nanmax(seg))
        ypad = 0.08 * max(hi - lo, 1.0)
        self.plot.setXRange(float(t_rel[0]), float(t_rel[-1]), padding=0.02)
        self.plot.setYRange(lo - ypad, hi + ypad, padding=0.02)

        parts = [f"t1 {t1:.4f} s", f"dwell {_num(row, 'toff'):.3f} ms",
                 f"ΔI {_num(row, 'mean'):.1f} pA"]
        if np.isfinite(io):
            parts.append(f"Io {io:.1f} pA")
        st = row.get("state", "") if hasattr(row, "get") else ""
        if st:
            parts.append(f"state {st}")
        reason = row.get("drop_reason", "") if hasattr(row, "get") else ""
        if reason:
            parts.append(f"剔除：{reason}")
        self._title.setText("   ".join(parts))

    # ---- internals -------------------------------------------------------
    def _clear_markers(self) -> None:
        for it in self._markers:
            self.plot.removeItem(it)
        self._markers = []
