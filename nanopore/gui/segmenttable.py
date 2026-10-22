"""Selected-event fingerprint table (one row per segment).

Sits beside the zoom slice. Selecting an event fills the rows from its
:class:`nanopore.describe.EventDescription`; clicking a row asks the slice to
emphasize that segment.
"""
from __future__ import annotations

import math

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (QAbstractItemView, QLabel, QTableWidget,
                             QTableWidgetItem, QVBoxLayout, QWidget)

HEADERS = ["段", "起 (ms)", "止 (ms)", "宽 (ms)", "电平 (pA)",
           "相对 (pA)", "跃变 (pA)", "SNR"]

HINT_OFF = "未启用事件指纹：在「参数 → 输出」勾选「事件指纹（分段）」。"
HINT_NONE = "该事件没有分段（可能过短或描述器判定无效）。"


def _fmt(value, digits: int = 1) -> str:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—"
    return "—" if not math.isfinite(v) else f"{v:.{digits}f}"


class SegmentTable(QWidget):
    segment_selected = pyqtSignal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._title = QLabel("事件指纹")
        self._title.setStyleSheet("font-weight:600; padding:2px 4px;")
        self._hint = QLabel(HINT_OFF)
        self._hint.setWordWrap(True)
        self._hint.setStyleSheet("color:#57606a; padding:2px 4px;")

        self.table = QTableWidget(0, len(HEADERS))
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        for col, width in enumerate((36, 66, 66, 66, 78, 78, 78, 56)):
            self.table.setColumnWidth(col, width)
        self.table.cellClicked.connect(self._on_click)
        self.table.setVisible(False)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.addWidget(self._title)
        lay.addWidget(self._hint)
        lay.addWidget(self.table, 1)

    def clear(self, message: str = HINT_OFF) -> None:
        self.table.setRowCount(0)
        self.table.setVisible(False)
        self._hint.setText(message)
        self._hint.setVisible(True)
        self._title.setText("事件指纹")

    def set_pending(self) -> None:
        self.clear("正在计算该事件的指纹 …")

    def set_description(self, desc, fs: float) -> None:
        """Fill rows from an EventDescription (or show a hint when absent)."""
        if desc is None:
            self.clear(HINT_OFF)
            return
        segs = getattr(desc, "segments", None) or []
        self._title.setText(f"事件指纹 · 事件 #{desc.event_id} · {len(segs)} 段")
        if not segs:
            self.clear(HINT_NONE)
            return
        self._hint.setVisible(False)
        self.table.setVisible(True)
        self.table.setRowCount(len(segs))
        for row, seg in enumerate(segs):
            values = [
                str(row + 1),
                _fmt(seg.start / fs * 1000.0),
                _fmt(seg.end / fs * 1000.0),
                _fmt(seg.width_samples / fs * 1000.0),
                _fmt(seg.level_pA),
                _fmt(seg.level_rel),
                _fmt(seg.attrs.get("amp_pA")),
                _fmt(seg.attrs.get("snr"), 2),
            ]
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(row, col, item)
        self.table.clearSelection()

    def _on_click(self, row: int, _col: int) -> None:
        self.segment_selected.emit(row)
