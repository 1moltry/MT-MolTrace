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
from .segmenttable import SegmentTable
from .sliceview import SliceView
from .waveview import WaveView
from ..registry import get_detector


class MainWindow(QMainWindow):
    home_requested = pyqtSignal()

    def __init__(self, data: str | None = None, detector: str | None = None) -> None:
        super().__init__()
        self.setWindowTitle("MOLTRACE · 摩尔迹 — 分析界面")

        # centre: full trace on top, selected-event zoom slice + segment table below
        self.wave = WaveView()
        self.slice = SliceView()
        self.segments = SegmentTable()
        bottom = QSplitter(Qt.Horizontal)
        bottom.addWidget(self.slice)
        bottom.addWidget(self.segments)
        bottom.setStretchFactor(0, 3)
        bottom.setStretchFactor(1, 1)
        split = QSplitter(Qt.Vertical)
        split.addWidget(self.wave)
        split.addWidget(bottom)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        self.setCentralWidget(split)

        self.event = EventTable()
        self.excluded = ExcludedView(on_select=self._show_excluded_row)
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
        self.dock_excluded = self._dock("剔除 / 异常事件", self.excluded, "dock_excluded")
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
        bus.description_ready.connect(self._on_description)
        bus.roi_rerun.connect(ctrl_mod.controller.rerun_roi)
        self.segments.describer_changed.connect(self._on_describer_changed)
        self.segments.comparison_changed.connect(self._on_comparison_changed)
        self.segments.compare_toggled.connect(self._on_compare_toggled)
        self._current_number: int | None = None
        self._export_worker = None

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
            (self.dock_excluded, "剔除 / 异常事件表"),
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
        self.params._save_settings()
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
        self.anomaly_label = QLabel("异常识别：关")
        self.anomaly_label.setStyleSheet("color:#8c6d1f; padding:0 10px;")
        self.anomaly_label.setToolTip(
            "异常识别是检测后的可选筛查，只剔除已检出事件，不改变任何检测边界。")
        bar.addWidget(self.anomaly_label)
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
        try:
            self.detector_desc.setText(get_detector(det).desc)
        except KeyError:
            self.detector_desc.setText("")

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

        self.act_fp = QAction("指纹分段", self)
        self.act_fp.setCheckable(True)
        self.act_fp.setChecked("describe" in self.params.enabled_ids())
        self.act_fp.setToolTip(
            "事件指纹（描述层）\n"
            "开：对每个保留事件做事件内分段（DP+BIC），切片图叠加分段，\n"
            "    批量处理时输出 <名>_fingerprints.xlsx / .json。\n"
            "首次开启或事件很多时，分析会明显变慢。")
        self.act_fp.toggled.connect(self._on_fingerprint_toggled)
        self.params.mod_changed.connect(self._on_mod_changed)
        self.segments.segment_selected.connect(self.slice.highlight_segment)
        bar.addSeparator()
        bar.addAction(self.act_fp)
        self.act_export = QAction("导出指纹…", self)
        self.act_export.setToolTip(
            "用当前描述器与参数为本次载入文件重新计算全部事件的分段，\n"
            "写出 <名>_fingerprints.xlsx / .json（与批量处理同一套列）。")
        self.act_export.triggered.connect(self._export_fingerprints)
        bar.addAction(self.act_export)

    def _on_fingerprint_toggled(self, enabled: bool) -> None:
        self.params.set_mod_enabled("describe", enabled)
        bus.status.emit("事件指纹已启用，正在重跑 …" if enabled else "事件指纹已关闭")

    def _on_mod_changed(self, mid: str, enabled: bool) -> None:
        if mid == "describe":
            self.act_fp.blockSignals(True)
            self.act_fp.setChecked(enabled)
            self.act_fp.blockSignals(False)

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

    def _export_fingerprints(self) -> None:
        """Write this file's fingerprints with the same writer the batch uses."""
        c = ctrl_mod.controller
        if c.rec is None or c.analysis is None:
            bus.status.emit("请先打开一个 .abf 文件")
            return
        out = QFileDialog.getExistingDirectory(self, "选择指纹导出目录")
        if not out:
            return
        cfg = self.params.build_config()
        if "describe" not in cfg.enabled_mods:
            # The user explicitly asked for fingerprints; enable the mod so the
            # protocol that produced the files is self-describing.
            self.params.set_mod_enabled("describe", True)
            cfg = self.params.build_config()
        c.set_config(cfg)
        worker = ctrl_mod.ExportDescriptionsWorker(c.analysis, c.rec, Path(out), cfg)
        self._export_worker = worker
        worker.progress.connect(
            lambda i, n: bus.status.emit(f"导出指纹 {i}/{n} …"))
        worker.done.connect(
            lambda paths: bus.status.emit(f"指纹已导出: {paths['xlsx']}"))
        worker.failed.connect(
            lambda msg: bus.status.emit(f"导出失败: {msg}"))
        bus.status.emit("正在计算并导出指纹 …")
        worker.start()

    # ---- results / selection ---------------------------------------------
    def _on_results(self) -> None:
        c = ctrl_mod.controller
        self.wave.set_data(c.rec, c.lv, c.df, c.anom)
        self.scatter.set_data(c.df)
        self.event.set_data(c.df)
        analysis = getattr(c, "analysis", None)
        anomaly_enabled = (analysis.anomaly_enabled
                           if analysis is not None else False)
        detector_rejected = (analysis.detector_rejected
                             if analysis is not None else 0)
        self.excluded.set_data(
            c.df_excluded, anomaly_enabled=anomaly_enabled,
            detector_rejected=detector_rejected)
        self.slice.clear()
        self.segments.set_current_describer(c.cfg.describer or "dp_bic")
        self.segments.clear()
        self._current_number = None

        det_id = (analysis.detector_id if analysis is not None
                  else self.params.current_detector())
        try:
            det_label = get_detector(det_id).label
        except KeyError:
            det_label = det_id
        n_raw = len(c.det.events) if c.det is not None else 0
        n_keep = len(c.df) if c.df is not None else 0
        n_exc = len(c.df_excluded) if c.df_excluded is not None else 0
        stage_counts: dict[str, int] = {}
        if c.df_excluded is not None and "drop_stage" in c.df_excluded.columns:
            for stage in c.df_excluded["drop_stage"]:
                for part in str(stage).split("+"):
                    if part:
                        stage_counts[part] = stage_counts.get(part, 0) + 1
        detail = []
        for key, label in (("anomaly", "异常"), ("toff", "时长"),
                           ("detector", "检测规则")):
            if stage_counts.get(key):
                detail.append(f"{label} {stage_counts[key]}")
        detail_text = f"（{' / '.join(detail)}）" if detail else ""
        self.summary_label.setText(
            f"{det_label} · 候选 {n_raw + detector_rejected} · "
            f"保留 {n_keep} · 剔除 {n_exc}{detail_text}")
        if anomaly_enabled:
            self.anomaly_label.setText("异常识别：开（仅后处理）")
            self.anomaly_label.setStyleSheet("color:#116329; padding:0 10px;")
            if det_id == "burst":
                self.anomaly_label.setToolTip(
                    "burst 的事件边界在异常识别之前确定；异常只会剔除事件，"
                    "不会改变 burst 的检测结果。")
        else:
            self.anomaly_label.setText("异常识别：关")
            self.anomaly_label.setStyleSheet("color:#8c6d1f; padding:0 10px;")
            self.anomaly_label.setToolTip(
                "本次未筛查反压、膜抖、炸膜或漂移；剔除数只代表检测规则与时长过滤。")
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
        self._current_number = idx + 1
        self._show_row(c.df.iloc[idx], idx + 1)
        c.describe_event(idx, self.segments.current_describer())
        if self.segments.is_comparing():
            c.describe_event(idx, self.segments.comparison_describer())

    def _on_description(self, event_id: int, desc, describer_id: str = "") -> None:
        """Fill the slice/table when the selected event's description arrives."""
        if event_id != self._current_number:
            return
        c = ctrl_mod.controller
        idx = event_id - 1
        if c.df is None or not (0 <= idx < len(c.df)) or c.rec is None:
            return
        sr = c.rec.sample_rate_hz
        primary = self.segments.current_describer()
        compare = (self.segments.comparison_describer()
                   if self.segments.is_comparing() else None)
        if describer_id == primary:
            self.slice.set_row(c.df.iloc[idx], c.rec.current, sr,
                               number=event_id, desc=desc)
            self.segments.set_description(desc, sr, describer_id)
            if compare and compare != primary:
                c.describe_event(idx, compare)
        elif compare and describer_id == compare:
            self.segments.set_comparison(desc, sr, describer_id)

    def _on_describer_changed(self, describer_id: str) -> None:
        """The segment table switched describers: reuse the event, redescription only."""
        self.params.set_describer(describer_id, notify=False)
        c = ctrl_mod.controller
        c.set_config(self.params.build_config())
        if self._current_number is not None:
            c.describe_event(self._current_number - 1, describer_id)

    def _on_comparison_changed(self, describer_id: str) -> None:
        if self._current_number is not None:
            ctrl_mod.controller.describe_event(self._current_number - 1,
                                               describer_id)

    def _on_compare_toggled(self, enabled: bool) -> None:
        if not enabled:
            self.segments.set_comparison(None, 0.0)
            return
        if self._current_number is not None:
            idx = self._current_number - 1
            c = ctrl_mod.controller
            c.describe_event(idx, self.segments.current_describer())
            if self.segments.comparison_describer() != self.segments.current_describer():
                c.describe_event(idx, self.segments.comparison_describer())

    def closeEvent(self, event) -> None:       # noqa: N802 — Qt signature
        """When opened from the home workbench, X returns there instead of quitting."""
        if getattr(self, "return_to_home_on_close", False):
            self.return_to_home_on_close = False
            event.ignore()
            self.home_requested.emit()
            return
        super().closeEvent(event)

    def _show_excluded_row(self, row, _number: int | None = None) -> None:
        """Review a removed event without borrowing a kept event's fingerprint."""
        self._current_number = None
        self.event.view.clearSelection()
        self._show_row(row, number=None)

    def _show_row(self, row, number: int | None = None) -> None:
        """Focus the main view on an event span (pan, no zoom) + fill the slice."""
        c = ctrl_mod.controller
        self.wave.focus_event(float(row["t1"]), float(row["t2"]))
        desc = None
        did = self.segments.current_describer()
        if number is not None:
            desc = c.cached_description(number - 1, did)
        sr = c.rec.sample_rate_hz if c.rec is not None else 0.0
        self.slice.set_row(row, c.rec.current if c.rec is not None else None,
                           sr, number=number, desc=desc)
        if desc is not None:
            self.segments.set_description(desc, sr, did)
        elif number is not None and "describe" in c.cfg.enabled_mods:
            self.segments.set_pending()
        else:
            self.segments.clear()
        if number is not None and self.segments.is_comparing():
            compare = self.segments.comparison_describer()
            desc_b = c.cached_description(number - 1, compare)
            if desc_b is not None:
                self.segments.set_comparison(desc_b, sr, compare)
            else:
                # never leave the previous event's comparison rows visible
                self.segments.set_comparison(None, sr)
