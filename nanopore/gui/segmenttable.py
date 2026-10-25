"""Selected-event fingerprint table (one row per segment).

Sits beside the zoom slice. Selecting an event fills the rows from its
:class:`nanopore.fingerprint.EventDescription`; clicking a row asks the slice
to emphasize that segment.

The describer list comes from the shared registry. A second table can be shown
side by side so two describers on the same event can be compared without
recomputing the event detection.
"""
from __future__ import annotations

import math

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QHBoxLayout,
                             QLabel, QSplitter, QTableWidget, QTableWidgetItem,
                             QVBoxLayout, QWidget)

from ..fingerprint import describe_meta

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


def _describer_items() -> list[tuple[str, str]]:
    items = []
    for info in describe_meta():
        suffix = {"beta": "（测试）",
                  "experimental": "（实验性）"}.get(info["maturity"], "")
        items.append((info["label"] + suffix, info["id"]))
    return items


class SegmentTable(QWidget):
    segment_selected = pyqtSignal(int)
    describer_changed = pyqtSignal(str)
    comparison_changed = pyqtSignal(str)
    compare_toggled = pyqtSignal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._title = QLabel("事件指纹")
        self._title.setStyleSheet("font-weight:600; padding:2px 4px;")

        self.describer_combo = QComboBox()
        self.compare_combo = QComboBox()
        for label, did in _describer_items():
            self.describer_combo.addItem(label, did)
            self.compare_combo.addItem(label, did)
        idx = self.describer_combo.findData("dp_bic")
        self.describer_combo.setCurrentIndex(idx if idx >= 0 else 0)
        cc = self.compare_combo.findData("classic")
        self.compare_combo.setCurrentIndex(cc if cc >= 0 else 0)
        self.compare_combo.setVisible(False)
        self.compare_box = QCheckBox("并排比较")
        self.compare_box.setToolTip(
            "并排显示两种描述器在同一事件上的分段；只重算描述，不重跑事件检测。")

        row = QHBoxLayout()
        row.setContentsMargins(2, 0, 2, 0)
        row.addWidget(QLabel("描述器"))
        row.addWidget(self.describer_combo, 1)
        row.addWidget(self.compare_box)
        row.addWidget(self.compare_combo, 1)

        self._hint = QLabel(HINT_OFF)
        self._hint.setWordWrap(True)
        self._hint.setStyleSheet("color:#57606a; padding:2px 4px;")

        self._label_a = QLabel("")
        self._label_b = QLabel("")
        for lab in (self._label_a, self._label_b):
            lab.setStyleSheet("color:#57606a; padding:0 4px;")

        self.table = self._make_table()
        self.table_b = self._make_table()
        self.table.cellClicked.connect(self._on_click)
        self.table_b.cellClicked.connect(self._on_click)
        self.table_b.setVisible(False)

        box_a = QWidget()
        lay_a = QVBoxLayout(box_a)
        lay_a.setContentsMargins(0, 0, 0, 0)
        lay_a.addWidget(self._label_a)
        lay_a.addWidget(self.table, 1)
        box_b = QWidget()
        lay_b = QVBoxLayout(box_b)
        lay_b.setContentsMargins(0, 0, 0, 0)
        lay_b.addWidget(self._label_b)
        lay_b.addWidget(self.table_b, 1)
        box_b.setVisible(False)
        self._box_b = box_b
        self._split = QSplitter(Qt.Horizontal)
        self._split.addWidget(box_a)
        self._split.addWidget(box_b)
        self._split.setStretchFactor(0, 1)
        self._split.setStretchFactor(1, 1)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.addWidget(self._title)
        lay.addLayout(row)
        lay.addWidget(self._hint)
        lay.addWidget(self._split, 1)

        self.table_b.setVisible(False)
        self._split.setVisible(False)
        self.describer_combo.currentIndexChanged.connect(self._on_describer)
        self.compare_combo.currentIndexChanged.connect(self._on_comparison)
        self.compare_box.toggled.connect(self._on_compare_toggled)

    @staticmethod
    def _make_table() -> QTableWidget:
        table = QTableWidget(0, len(HEADERS))
        table.setHorizontalHeaderLabels(HEADERS)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setStretchLastSection(True)
        for col, width in enumerate((36, 66, 66, 66, 78, 78, 78, 56)):
            table.setColumnWidth(col, width)
        return table

    # ---- describer selection -------------------------------------------
    def current_describer(self) -> str:
        return str(self.describer_combo.currentData())

    def comparison_describer(self) -> str:
        return str(self.compare_combo.currentData())

    def set_current_describer(self, describer_id: str) -> None:
        idx = self.describer_combo.findData(describer_id)
        if idx >= 0 and idx != self.describer_combo.currentIndex():
            self.describer_combo.blockSignals(True)
            self.describer_combo.setCurrentIndex(idx)
            self.describer_combo.blockSignals(False)

    def _ensure_distinct_comparison(self) -> None:
        """Keep the comparison describer different from the primary one."""
        if self.comparison_describer() != self.current_describer():
            return
        for _label, did in _describer_items():
            if did != self.current_describer():
                idx = self.compare_combo.findData(did)
                self.compare_combo.blockSignals(True)
                self.compare_combo.setCurrentIndex(idx)
                self.compare_combo.blockSignals(False)
                return

    def _on_describer(self, *_args) -> None:
        if self.is_comparing():
            self._ensure_distinct_comparison()
        self.describer_changed.emit(self.current_describer())
        if self.is_comparing():
            self.comparison_changed.emit(self.comparison_describer())

    def _on_comparison(self, *_args) -> None:
        if self.compare_box.isChecked():
            self.comparison_changed.emit(self.comparison_describer())

    def _on_compare_toggled(self, enabled: bool) -> None:
        self.compare_combo.setVisible(enabled)
        self._box_b.setVisible(enabled)
        self._split.setVisible(enabled)
        if enabled:
            self._ensure_distinct_comparison()
            self.comparison_changed.emit(self.comparison_describer())
        self.compare_toggled.emit(enabled)

    def is_comparing(self) -> bool:
        return bool(self.compare_box.isChecked())

    # ---- data ----------------------------------------------------------
    def clear(self, message: str = HINT_OFF) -> None:
        for table in (self.table, self.table_b):
            table.setRowCount(0)
        self._label_a.setText("")
        self._label_b.setText("")
        self.table.setVisible(False)
        self.table_b.setVisible(False)
        self._split.setVisible(False)
        self._hint.setText(message)
        self._hint.setVisible(True)
        self._title.setText("事件指纹")

    def set_pending(self) -> None:
        self.clear("正在计算该事件的指纹 …")

    def _fill(self, table: QTableWidget, desc, fs: float) -> int:
        segs = getattr(desc, "segments", None) or []
        table.setRowCount(len(segs))
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
                table.setItem(row, col, item)
        table.clearSelection()
        return len(segs)

    def set_description(self, desc, fs: float, describer_id: str | None = None) -> None:
        """Fill the primary table from an EventDescription (or show a hint)."""
        if desc is None:
            self.clear(HINT_OFF)
            return
        did = describer_id or getattr(desc, "describer", "") or self.current_describer()
        self.set_current_describer(did)
        self._title.setText(f"事件指纹 · 事件 #{desc.event_id}")
        self._label_a.setText(did)
        n = self._fill(self.table, desc, fs)
        if n == 0:
            reason = str((getattr(desc, "quality", None) or {}).get("reason", "") or "")
            self.table.setVisible(False)
            self._hint.setText(reason or HINT_NONE)
            self._hint.setVisible(True)
        else:
            self.table.setVisible(True)
            self._hint.setVisible(False)
        self._split.setVisible(self.is_comparing() and n > 0)

    def set_comparison(self, desc, fs: float, describer_id: str | None = None) -> None:
        """Fill the secondary table used by side-by-side comparison."""
        if desc is None:
            self.table_b.setRowCount(0)
            self._label_b.setText("")
            self.table_b.setVisible(False)
            return
        did = describer_id or getattr(desc, "describer", "") or self.comparison_describer()
        self._label_b.setText(did)
        n = self._fill(self.table_b, desc, fs)
        self.table_b.setVisible(bool(n))
        self._box_b.setVisible(self.is_comparing())
        self._split.setVisible(self.is_comparing())

    def _on_click(self, row: int, _col: int) -> None:
        self.segment_selected.emit(row)
