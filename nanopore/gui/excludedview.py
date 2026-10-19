"""Excluded-events table (the "异常事件表").

One row per removed event with its ``drop_reason``. Clicking a row focuses the
main view on that event's span (pan, no zoom) and shows it in the zoom slice,
so a removed event is reviewed against the same detail as a kept one.
"""

from __future__ import annotations

from PyQt5.QtCore import QAbstractTableModel, QModelIndex, Qt
from PyQt5.QtWidgets import (QLabel, QTableView, QVBoxLayout, QWidget)

COLS = ["t1", "t2", "toff", "mean", "Io", "state", "drop_reason"]


class ExcludedModel(QAbstractTableModel):
    def __init__(self) -> None:
        super().__init__()
        self._df = None

    def set_df(self, df) -> None:
        self.beginResetModel()
        self._df = df
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if self._df is None else len(self._df)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(COLS) + 1                     # +1 for the 序号 column

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return "序号" if section == 0 else COLS[section - 1]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or self._df is None:
            return None
        if role == Qt.UserRole:
            return int(index.row())
        if role == Qt.DisplayRole:
            if index.column() == 0:
                return str(index.row() + 1)
            v = self._df.iloc[index.row()][COLS[index.column() - 1]]
            if isinstance(v, float):
                return "nan" if v != v else f"{v:.4g}"
            return str(v)
        if role == Qt.TextAlignmentRole:
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return None


class ExcludedView(QWidget):
    def __init__(self, on_select=None, parent=None) -> None:
        super().__init__(parent)
        self._on_select = on_select
        self._df = None
        self.model = ExcludedModel()
        self.view = QTableView()
        self.view.setModel(self.model)
        self.view.setSelectionBehavior(QTableView.SelectRows)
        self.view.setSelectionMode(QTableView.SingleSelection)
        self.view.horizontalHeader().setStretchLastSection(True)

        self.summary = QLabel("")
        self.summary.setWordWrap(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.summary)
        lay.addWidget(self.view)

        self.view.selectionModel().currentChanged.connect(self._row_changed)

    def set_data(self, excluded) -> None:
        self._df = excluded
        self.model.set_df(excluded)
        self.view.resizeColumnsToContents()
        if excluded is None or len(excluded) == 0:
            self.summary.setText("剔除事件 0")
            return
        by = excluded["drop_reason"].value_counts()
        self.summary.setText(f"剔除事件 {len(excluded)}："
                             + "，".join(f"{k}×{v}" for k, v in by.items()))

    def _row_changed(self, current: QModelIndex, previous: QModelIndex) -> None:
        if not current.isValid() or self._df is None or self._on_select is None:
            return
        i = self.model.data(current, Qt.UserRole)
        if isinstance(i, int) and 0 <= i < len(self._df):
            self._on_select(self._df.iloc[i], i + 1)   # (row, 1-based 序号)
