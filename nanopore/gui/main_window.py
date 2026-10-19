"""Main window.

Layout (mirrors the review workflow 波形 → 事件 → 事件指纹):

    left   : 事件表 (top)  +  异常事件（剔除）表 (bottom)
    centre : 全程波形 (top) + 选中事件的放大切片 (bottom, splitter)
    right  : 参数面板 (top) + 统计(直方图/散点) (bottom)

Selecting an event — from the wave (click), the event table, the excluded
table or the scatter — focuses the main view on that span **without changing
the zoom** (pan only; toggle the toolbar to auto-zoom), fills the zoom slice,
and syncs the other panels.
"""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QAction, QDockWidget, QFileDialog, QMainWindow,
                             QSplitter, QToolBar)

from . import controller as ctrl_mod
from .bus import bus
from .eventtable import EventTable
from .excludedview import ExcludedView
from .parampanel import ParamPanel
from .scatterview import ScatterView
from .sliceview import SliceView
from .waveview import WaveView


class MainWindow(QMainWindow):
    def __init__(self, data: str | None = None) -> None:
        super().__init__()
        self.setWindowTitle("SDL 纳米孔分析 — 交互式分析界面")

        # centre: full trace on top, selected-event zoom slice below
        self.wave = WaveView()
        self.slice = SliceView()
        split = QSplitter(Qt.Vertical)
        split.addWidget(self.wave)
        split.addWidget(self.slice)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        self.setCentralWidget(split)

        self.event = EventTable()
        self.excluded = ExcludedView(on_select=self._show_row)
        self.params = ParamPanel()
        self.scatter = ScatterView()

        self.addDockWidget(Qt.LeftDockWidgetArea, self._dock("事件", self.event))
        self.addDockWidget(Qt.LeftDockWidgetArea, self._dock("异常事件（剔除）", self.excluded))
        self.addDockWidget(Qt.RightDockWidgetArea, self._dock("参数", self.params))
        self.addDockWidget(Qt.RightDockWidgetArea, self._dock("统计 (直方图/散点)", self.scatter))

        self._build_toolbar()

        bus.status.connect(self.statusBar().showMessage)
        bus.detection_finished.connect(self._on_results)
        bus.event_selected.connect(self._on_select)
        bus.roi_rerun.connect(ctrl_mod.controller.rerun_roi)

        if data:
            ctrl_mod.controller.load(data)

    def _dock(self, title: str, widget) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setWidget(widget)
        return dock

    def _build_toolbar(self) -> None:
        bar = QToolBar("main")
        bar.setMovable(False)
        self.addToolBar(bar)

        act_open = QAction("打开", self)
        act_open.triggered.connect(self._open)
        bar.addAction(act_open)

        act_run = QAction("重跑", self)
        act_run.triggered.connect(self.params._run)
        bar.addAction(act_run)

        act_fit = QAction("全览", self)
        act_fit.triggered.connect(self.wave.autoscale)
        bar.addAction(act_fit)

        act_batch = QAction("批量处理…", self)
        act_batch.triggered.connect(self._batch)
        bar.addAction(act_batch)

        # selecting an event pans (default) or zooms the main view
        self.act_follow = QAction("选中时自适应缩放", self)
        self.act_follow.setCheckable(True)
        self.act_follow.setChecked(False)
        self.act_follow.setToolTip(
            "关（默认）：选中事件时主视图**跳转**到该事件，保持你当前的缩放级别不变。\n"
            "开：选中时主视图额外自适应缩放到刚好容纳该事件。")
        self.act_follow.toggled.connect(self.wave.set_zoom_on_select)
        bar.addAction(self.act_follow)

    # ---- file / batch ----------------------------------------------------
    def _open(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "打开 .abf", "", "ABF (*.abf)")
        if path:
            ctrl_mod.controller.load(path)

    def _batch(self) -> None:
        from .batchdialog import BatchDialog

        dlg = BatchDialog(self.params.build_config(), self)
        dlg.exec_()

    # ---- results / selection ---------------------------------------------
    def _on_results(self) -> None:
        c = ctrl_mod.controller
        self.wave.set_data(c.rec, c.lv, c.df, c.anom)
        self.scatter.set_data(c.df)
        self.event.set_data(c.df)
        self.excluded.set_data(c.df_excluded)
        self.slice.clear()

    def _on_select(self, idx: int) -> None:
        c = ctrl_mod.controller
        if c.df is None or not (0 <= idx < len(c.df)):
            return
        self.event.select_row(idx)
        self.scatter.highlight(idx)
        self._show_row(c.df.iloc[idx])

    def _show_row(self, row) -> None:
        """Focus the main view on an event span (pan, no zoom) + fill the slice."""
        c = ctrl_mod.controller
        self.wave.focus_event(float(row["t1"]), float(row["t2"]))
        self.slice.set_row(row,
                           c.rec.current if c.rec is not None else None,
                           c.rec.sample_rate_hz if c.rec is not None else 0.0)
