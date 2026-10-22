"""Main window.

Layout (mirrors the review workflow 波形 → 事件 → 事件指纹):

    left   : 事件表 (top)  +  异常事件（剔除）表 (bottom, hidden by default)
    centre : 全程波形 (top) + 选中事件的放大切片 (bottom, splitter)
    right  : 参数面板 (top) + 统计(直方图/散点) (bottom, hidden by default)

The 视图 menu toggles every dock; the two secondary panels start hidden so the
waveform keeps the space. Selecting an event — from the wave (click), the event
table, the excluded table or the scatter — focuses the main view on that span
**without changing the zoom** (pan only; toggle the toolbar to auto-zoom),
fills the zoom slice, and syncs the other panels.
"""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (QAction, QDockWidget, QFileDialog, QLabel,
                             QMainWindow, QSplitter, QToolBar)

from . import controller as ctrl_mod
from . import history
from .bus import bus
from .eventtable import EventTable
from .excludedview import ExcludedView
from .parampanel import ParamPanel
from .scatterview import ScatterView
from .sliceview import SliceView
from .waveview import WaveView

_DETECTOR_LABELS = {
    "level": "电平法",
    "burst": "驻留包络（burst）",
    "plateau": "平台滞回",
}
_DETECTOR_DESC = {
    "level": "逐样本最近电平；边界在 50% 交叉。适合常规、多电平、肽信号。",
    "burst": "驻留包络去抖；把毛刺和上下跳合并。适合抖动、碎片化阻孔。",
    "plateau": "边界贴近开孔；部分恢复不切碎事件。适合糖、长阻孔信号。",
}


class MainWindow(QMainWindow):
    home_requested = pyqtSignal()

    def __init__(self, data: str | None = None, detector: str | None = None) -> None:
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

        # option edits apply automatically: debounce briefly, then re-analyse
        self._auto = QTimer(self)
        self._auto.setSingleShot(True)
        self._auto.setInterval(600)
        self._auto.timeout.connect(self._auto_rerun)
        self.params.changed.connect(self._schedule_auto_rerun)
        self.params.run.clicked.connect(lambda: self._auto.stop())

        self.dock_event = self._dock("事件", self.event, "dock_event")
        self.dock_excluded = self._dock("异常事件（剔除）", self.excluded, "dock_excluded")
        self.dock_params = self._dock("参数", self.params, "dock_params")
        self.dock_scatter = self._dock("统计 (直方图/散点)", self.scatter, "dock_scatter")
        self.addDockWidget(Qt.LeftDockWidgetArea, self.dock_event)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.dock_excluded)
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock_params)
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock_scatter)
        self._build_view_menu()

        self._build_workflow_bar()
        self._build_toolbar()

        bus.status.connect(self.statusBar().showMessage)
        bus.detection_finished.connect(self._on_results)
        bus.event_selected.connect(self._on_select)
        bus.roi_rerun.connect(ctrl_mod.controller.rerun_roi)

        if detector:
            self.params.set_detector(detector)
            self._on_detector_changed()
        if data:
            ctrl_mod.controller.load(data, self.params.build_config())

    def _dock(self, title: str, widget, name: str) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setObjectName(name)
        dock.setWidget(widget)
        return dock

    def _build_view_menu(self) -> None:
        menu = self.menuBar().addMenu("视图")
        for dock, label in (
            (self.dock_event, "事件表"),
            (self.dock_excluded, "异常事件表"),
            (self.dock_params, "参数面板"),
            (self.dock_scatter, "统计图"),
        ):
            act = dock.toggleViewAction()
            act.setText(label)
            menu.addAction(act)
            dock.visibilityChanged.connect(
                lambda visible, w=dock.widget(): w.update() if visible else None)
        self.dock_excluded.hide()
        self.dock_scatter.hide()

    # ---- live apply ------------------------------------------------------
    def _schedule_auto_rerun(self) -> None:
        if ctrl_mod.controller.rec is None:
            return
        self._auto.start()             # restart the debounce window

    def _auto_rerun(self) -> None:
        c = ctrl_mod.controller
        if c.rec is None:
            return
        c.set_config(self.params.build_config())
        bus.status.emit("参数已更改，自动重跑 …")
        c.rerun()

    def _build_workflow_bar(self) -> None:
        """Top bar: the four user-facing decisions, left to right."""
        bar = QToolBar("workflow")
        bar.setMovable(False)
        self.addToolBar(bar)

        act_home = QAction("首页", self)
        act_home.triggered.connect(self.home_requested.emit)
        bar.addAction(act_home)

        act_open = QAction("打开…", self)
        act_open.triggered.connect(self._open)
        bar.addAction(act_open)

        self.path_label = QLabel("（未打开文件）")
        self.path_label.setStyleSheet("color:#57606a; padding:0 10px;")
        bar.addWidget(self.path_label)
        bar.addSeparator()

        bar.addWidget(QLabel("检测算法 "))
        bar.addWidget(self.params.event_mode)
        self.detector_desc = QLabel("")
        self.detector_desc.setStyleSheet("color:#57606a; padding:0 10px;")
        bar.addWidget(self.detector_desc)
        bar.addSeparator()

        act_cmp = QAction("算法对比…", self)
        act_cmp.triggered.connect(self._compare)
        bar.addAction(act_cmp)

        act_batch = QAction("批量处理…", self)
        act_batch.triggered.connect(self._batch)
        bar.addAction(act_batch)

        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet("font-weight:600; padding:0 10px;")
        bar.addWidget(self.summary_label)

        self.params.event_mode.currentIndexChanged.connect(self._on_detector_changed)
        self._on_detector_changed()

    def _on_detector_changed(self) -> None:
        det = self.params.current_detector()
        self.detector_desc.setText(_DETECTOR_DESC.get(det, ""))

    def set_detector(self, detector: str) -> None:
        """Select an algorithm from outside (compare dialog / home card)."""
        self.params.set_detector(detector)
        self._on_detector_changed()

    def _build_toolbar(self) -> None:
        bar = QToolBar("view")
        bar.setMovable(False)
        self.addToolBar(bar)

        act_run = QAction("重跑", self)
        act_run.triggered.connect(self.params._run)
        act_run.triggered.connect(lambda: self._auto.stop())
        bar.addAction(act_run)

        act_fit = QAction("全览", self)
        act_fit.triggered.connect(self.wave.autoscale)
        bar.addAction(act_fit)

        # selecting an event pans (default) or zooms the main view
        self.act_follow = QAction("选中时自适应缩放", self)
        self.act_follow.setCheckable(True)
        self.act_follow.setChecked(False)
        self.act_follow.setToolTip(
            "关（默认）：选中事件时主视图**跳转**到该事件，保持你当前的缩放级别不变。\n"
            "开：选中时主视图额外自适应缩放到刚好容纳该事件。")
        self.act_follow.toggled.connect(self.wave.set_zoom_on_select)
        bar.addAction(self.act_follow)

    # ---- file / batch / compare -----------------------------------------
    def _open(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "打开 .abf", "", "ABF (*.abf)")
        if path:
            ctrl_mod.controller.load(path, self.params.build_config())

    def _batch(self) -> None:
        from .batchdialog import BatchDialog

        dlg = BatchDialog(self.params.build_config(), self)
        dlg.exec_()

    def _compare(self) -> None:
        from .compare import CompareDialog

        c = ctrl_mod.controller
        dlg = CompareDialog(
            current_path=str(c.rec.path) if c.rec is not None else None,
            cfg=self.params.build_config(),
            parent=self,
        )
        dlg.use_detector.connect(self.set_detector)
        dlg.exec_()

    # ---- results / selection ---------------------------------------------
    def _on_results(self) -> None:
        c = ctrl_mod.controller
        self.wave.set_data(c.rec, c.lv, c.df, c.anom)
        self.scatter.set_data(c.df)
        self.event.set_data(c.df)
        self.excluded.set_data(c.df_excluded)
        self.slice.clear()

        det = self.params.current_detector()
        n_raw = len(c.det.events) if c.det is not None else 0
        n_keep = len(c.df) if c.df is not None else 0
        n_exc = len(c.df_excluded) if c.df_excluded is not None else 0
        self.summary_label.setText(
            f"{_DETECTOR_LABELS.get(det, det)} · 检出 {n_raw} · "
            f"保留 {n_keep} · 剔除 {n_exc}")
        if c.rec is not None:
            self.path_label.setText(Path(c.rec.path).name)
            self.path_label.setToolTip(str(c.rec.path))
            history.add_recent(c.rec.path)

    def _on_select(self, idx: int) -> None:
        c = ctrl_mod.controller
        if c.df is None or not (0 <= idx < len(c.df)):
            return
        self.event.select_row(idx)
        self.scatter.highlight(idx)
        self._show_row(c.df.iloc[idx], idx + 1)

    def closeEvent(self, event) -> None:       # noqa: N802 — Qt signature
        """When opened from the home workbench, X returns there instead of quitting."""
        if getattr(self, "return_to_home_on_close", False):
            self.return_to_home_on_close = False
            event.ignore()
            self.home_requested.emit()
            return
        super().closeEvent(event)

    def _show_row(self, row, number: int | None = None) -> None:
        """Focus the main view on an event span (pan, no zoom) + fill the slice."""
        c = ctrl_mod.controller
        self.wave.focus_event(float(row["t1"]), float(row["t2"]))
        self.slice.set_row(row,
                           c.rec.current if c.rec is not None else None,
                           c.rec.sample_rate_hz if c.rec is not None else 0.0,
                           number=number)
