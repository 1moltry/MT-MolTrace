"""Experimental fingerprint research workspace.

Three tabs mirror the research pipeline:

* **语料** — pick .abf files/folders (or reuse the current analysis result),
  build a cross-event :class:`EventCorpus`;
* **词表** — fit a shape vocabulary, save/load it as JSON, inspect centers as
  thumbnails;
* **解码** — decode one corpus event with the active vocabulary and overlay the
  fragment spans on its body.

The window is explicit about its status: the legacy vocabulary did not pass the
planned AUC ≥ 0.85 gate, so everything is labelled experimental and nothing is
enabled by default. Missing ``research`` dependencies disable fitting/decoding
with an install hint instead of failing later.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pyqtgraph as pg
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (QComboBox, QDialog, QFileDialog, QFormLayout,
                             QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                             QListWidget, QMessageBox, QPlainTextEdit,
                             QPushButton, QScrollArea, QSpinBox, QTabWidget,
                             QTableWidget, QTableWidgetItem, QVBoxLayout,
                             QWidget)

from ..fingerprint import get_describer
from ..fingerprint.research import (EventCorpus, ShapeModel, build_corpus,
                                    fit_vocabulary, missing_dependencies,
                                    set_active_model)
from .parampanel import _param_widget, _widget_value

WARNING = ("实验性功能：旧形状词表在合成对照上的 AUC 为 0.674（N1tele）与 "
           "0.715（N2phase），低于计划门槛 0.85。结果只能用于探索，不得当作结论。")
COLORS = ("#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
          "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf")


class CorpusWorker(QThread):
    progress = pyqtSignal(int, int, str)
    done = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, paths: list[Path], cfg, limit: int):
        super().__init__()
        self.paths = paths
        self.cfg = cfg
        self.limit = int(limit)

    def run(self) -> None:
        try:
            corpus = build_corpus(
                self.paths, self.cfg, limit=self.limit,
                progress=lambda i, n, name: self.progress.emit(i, n, name))
            self.done.emit(corpus)
        except Exception as exc:  # noqa: BLE001 — keep the dialog alive
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class FitWorker(QThread):
    done = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, corpus: EventCorpus, params: dict):
        super().__init__()
        self.corpus = corpus
        self.params = params

    def run(self) -> None:
        try:
            self.done.emit(fit_vocabulary(self.corpus, self.params))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class ResearchDialog(QDialog):
    def __init__(self, cfg, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("指纹研究 · 实验性")
        self.resize(1120, 780)
        self._cfg = cfg
        self.corpus: EventCorpus | None = None
        self.model: ShapeModel | None = None
        self.method = get_describer("shape_vocab")
        self._corpus_worker: CorpusWorker | None = None
        self._fit_worker: FitWorker | None = None
        self._missing = missing_dependencies()

        warn = QLabel(WARNING)
        warn.setWordWrap(True)
        warn.setStyleSheet(
            "color:#8a4b00; background:#fff4e5; border:1px solid #f0c36d;"
            "border-radius:6px; padding:8px;")
        self.warn_label = warn
        self.dep_label = QLabel("")
        self.dep_label.setWordWrap(True)
        self.dep_label.setStyleSheet("color:#8b1a1a; padding:2px 4px;")
        if self._missing:
            self.dep_label.setText(
                "缺少实验性依赖：" + "、".join(self._missing)
                + "。语料构建仍可用；拟合/解码已禁用。安装：pip install -e \".[research]\"")
        else:
            self.dep_label.setText("实验性依赖已就绪（ruptures / scikit-learn）。")

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_corpus_tab(), "语料")
        self.tabs.addTab(self._build_vocab_tab(), "词表")
        self.tabs.addTab(self._build_decode_tab(), "解码")

        self.status = QLabel("先构建语料，再拟合词表，最后解码查看叠加。")
        self.status.setStyleSheet("color:#57606a; padding:2px 4px;")
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.reject)
        bottom = QHBoxLayout()
        bottom.addWidget(self.status, 1)
        bottom.addWidget(btn_close)

        lay = QVBoxLayout(self)
        lay.addWidget(warn)
        lay.addWidget(self.dep_label)
        lay.addWidget(self.tabs, 1)
        lay.addLayout(bottom)
        self._update_buttons()

    # ------------------------------------------------------------ corpus tab
    def _build_corpus_tab(self) -> QWidget:
        page = QWidget()
        self.file_list = QListWidget()
        add_files = QPushButton("添加文件…")
        add_dir = QPushButton("添加文件夹…")
        remove = QPushButton("移除选中")
        clear = QPushButton("清空")
        add_files.clicked.connect(self._add_files)
        add_dir.clicked.connect(self._add_dir)
        remove.clicked.connect(self._remove_selected)
        clear.clicked.connect(self.file_list.clear)
        row = QHBoxLayout()
        for b in (add_files, add_dir, remove, clear):
            row.addWidget(b)
        row.addStretch(1)

        self.limit = QSpinBox()
        self.limit.setRange(1, 100000)
        self.limit.setValue(200)
        self.limit.setToolTip("最多收集多少个保留事件；语料越大拟合越慢。")
        limit_row = QHBoxLayout()
        limit_row.addWidget(QLabel("事件上限"))
        limit_row.addWidget(self.limit)
        self.btn_current = QPushButton("使用当前分析结果")
        self.btn_current.clicked.connect(self._use_current_analysis)
        self.btn_build = QPushButton("构建语料")
        self.btn_build.clicked.connect(self._build_corpus)
        limit_row.addWidget(self.btn_current)
        limit_row.addStretch(1)
        limit_row.addWidget(self.btn_build)

        self.corpus_label = QLabel("尚未构建语料。")
        self.corpus_label.setWordWrap(True)
        self.corpus_label.setStyleSheet("color:#57606a;")
        self.corpus_log = QPlainTextEdit()
        self.corpus_log.setReadOnly(True)
        self.corpus_log.setMaximumHeight(120)

        lay = QVBoxLayout(page)
        lay.addLayout(row)
        lay.addWidget(self.file_list, 1)
        lay.addLayout(limit_row)
        lay.addWidget(self.corpus_label)
        lay.addWidget(self.corpus_log)
        return page

    # ------------------------------------------------------------- vocab tab
    def _build_vocab_tab(self) -> QWidget:
        page = QWidget()
        box = QGroupBox("拟合参数")
        form = QFormLayout(box)
        self.param_widgets: dict[str, QWidget] = {}
        for spec in self.method.params:
            w = _param_widget(spec)
            w.setToolTip(spec.desc or spec.label)
            self.param_widgets[spec.name] = w
            form.addRow(spec.label or spec.name, w)

        self.btn_fit = QPushButton("拟合词表")
        self.btn_fit.clicked.connect(self._fit)
        self.btn_save = QPushButton("保存词表…")
        self.btn_save.clicked.connect(self._save_model)
        self.btn_load = QPushButton("加载词表…")
        self.btn_load.clicked.connect(self._load_model)
        actions = QHBoxLayout()
        actions.addWidget(self.btn_fit)
        actions.addWidget(self.btn_save)
        actions.addWidget(self.btn_load)
        actions.addStretch(1)

        self.model_label = QLabel("尚未拟合词表。")
        self.model_label.setWordWrap(True)
        self.model_label.setStyleSheet("color:#57606a;")

        self.model_table = QTableWidget(0, 3)
        self.model_table.setHorizontalHeaderLabels(["形状", "支持度", "点数"])
        self.model_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.model_table.horizontalHeader().setStretchLastSection(True)
        self.model_table.setMaximumHeight(170)

        self.thumb_host = QWidget()
        self.thumb_grid = QGridLayout(self.thumb_host)
        self.thumb_grid.setContentsMargins(2, 2, 2, 2)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.thumb_host)

        lay = QVBoxLayout(page)
        lay.addWidget(box)
        lay.addLayout(actions)
        lay.addWidget(self.model_label)
        lay.addWidget(self.model_table)
        lay.addWidget(QLabel("词表缩略图（最多显示 12 个中心）"))
        lay.addWidget(scroll, 1)
        return page

    # ------------------------------------------------------------ decode tab
    def _build_decode_tab(self) -> QWidget:
        page = QWidget()
        self.event_combo = QComboBox()
        self.btn_decode = QPushButton("解码当前事件")
        self.btn_decode.clicked.connect(self._decode)
        row = QHBoxLayout()
        row.addWidget(QLabel("事件"))
        row.addWidget(self.event_combo, 1)
        row.addWidget(self.btn_decode)

        self.decode_plot = pg.PlotWidget()
        self.decode_plot.setBackground("w")
        self.decode_plot.showGrid(x=True, y=True, alpha=0.15)
        self.decode_plot.setLabel("bottom", "事件内时间", units="ms")
        self.decode_plot.setLabel("left", "电流", units="pA")
        self.decode_label = QLabel("选择事件后解码。")
        self.decode_label.setWordWrap(True)
        self.decode_label.setStyleSheet("color:#57606a;")

        self.decode_table = QTableWidget(0, 7)
        self.decode_table.setHorizontalHeaderLabels(
            ["段", "起 (ms)", "止 (ms)", "宽 (ms)", "中心", "距离", "接受"])
        self.decode_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.decode_table.horizontalHeader().setStretchLastSection(True)

        lay = QVBoxLayout(page)
        lay.addLayout(row)
        lay.addWidget(self.decode_plot, 3)
        lay.addWidget(self.decode_label)
        lay.addWidget(self.decode_table, 2)
        return page

    # --------------------------------------------------------------- helpers
    def _set_status(self, text: str) -> None:
        self.status.setText(text)

    def _update_buttons(self) -> None:
        deps = not self._missing
        busy = ((self._fit_worker is not None and self._fit_worker.isRunning())
                or (self._corpus_worker is not None and self._corpus_worker.isRunning()))
        self.btn_build.setEnabled(not busy)
        self.btn_fit.setEnabled(deps and self.corpus is not None and not busy)
        self.btn_decode.setEnabled(deps and self.corpus is not None
                                   and self.model is not None and not busy)
        self.btn_save.setEnabled(self.model is not None)
        self.btn_load.setEnabled(deps)
        self.btn_current.setEnabled(not busy)

    def _paths(self) -> list[Path]:
        out: dict[str, Path] = {}
        for i in range(self.file_list.count()):
            p = Path(self.file_list.item(i).text())
            if p.is_dir():
                for f in sorted(p.rglob("*.abf")):
                    out[str(f.resolve())] = f
            elif p.is_file():
                out[str(p.resolve())] = p
        return list(out.values())

    def _add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "选择 .abf 文件", "",
                                               "ABF (*.abf)")
        for p in paths:
            if not self._has(p):
                self.file_list.addItem(p)

    def _add_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "选择文件夹（递归搜集 .abf）")
        if d and not self._has(d):
            self.file_list.addItem(d)

    def _has(self, item: str) -> bool:
        return any(self.file_list.item(i).text() == item
                   for i in range(self.file_list.count()))

    def _remove_selected(self) -> None:
        for item in self.file_list.selectedItems():
            self.file_list.takeItem(self.file_list.row(item))

    def _on_corpus(self, corpus: EventCorpus) -> None:
        self.corpus = corpus
        self.corpus_log.clear()
        for err in corpus.meta.get("errors", []):
            self.corpus_log.appendPlainText(err)
        self.corpus_label.setText(
            f"语料：{corpus.n_events} 个事件，{len(corpus.source_names())} 个来源。")
        self.event_combo.clear()
        for i, (view, src) in enumerate(zip(corpus.views, corpus.sources)):
            self.event_combo.addItem(
                f"#{i + 1} {src} · 事件 {view.event_id} · "
                f"{view.duration_ms:.1f} ms", i)
        self._set_status(f"语料已就绪：{corpus.n_events} 个事件。")
        self._update_buttons()

    def _build_corpus(self) -> None:
        paths = self._paths()
        if not paths:
            QMessageBox.information(self, "指纹研究", "请先添加 .abf 文件或文件夹。")
            return
        self.btn_build.setEnabled(False)
        self._set_status("正在分析文件并构建语料 …")
        self._corpus_worker = CorpusWorker(paths, self._cfg, self.limit.value())
        self._corpus_worker.progress.connect(
            lambda i, n, name: self._set_status(f"语料 {i}/{n}: {name}"))
        self._corpus_worker.done.connect(self._on_corpus)
        self._corpus_worker.failed.connect(self._on_worker_failed)
        self._corpus_worker.finished.connect(lambda: self._update_buttons())
        self._corpus_worker.start()

    def _use_current_analysis(self) -> None:
        from . import controller as ctrl_mod

        analysis = ctrl_mod.controller.analysis
        if analysis is None:
            QMessageBox.information(
                self, "指纹研究", "主界面还没有完成分析；请先打开一个 .abf。")
            return
        self._on_corpus(EventCorpus.from_analysis(
            analysis, max_events=self.limit.value()))

    def _on_worker_failed(self, message: str) -> None:
        self._set_status("失败：" + message)
        QMessageBox.warning(self, "指纹研究", message)
        self._update_buttons()

    def _fit_params(self) -> dict:
        return {name: _widget_value(w) for name, w in self.param_widgets.items()}

    def _fit(self) -> None:
        if self.corpus is None:
            return
        self.btn_fit.setEnabled(False)
        self._set_status("正在拟合词表 …（片段越多越慢）")
        self._fit_worker = FitWorker(self.corpus, self._fit_params())
        self._fit_worker.done.connect(self._on_model)
        self._fit_worker.failed.connect(self._on_worker_failed)
        self._fit_worker.finished.connect(lambda: self._update_buttons())
        self._fit_worker.start()

    def _on_model(self, model: ShapeModel) -> None:
        self.model = model
        set_active_model(model)
        self.model_label.setText(
            f"词表 M={len(model.centers)} · 聚类阈值={model.threshold:.4g} · "
            f"模型 {model.model_id} · 来源 {len(model.sources)} 个。"
            + ("  ⚠ 支持度全部低于 min_support，已保留支持度最高的中心。"
               if model.metrics.get("below_min_support") else ""))
        self._set_status(
            "词表已拟合，并设为当前活动模型；可在主界面选择「形状词表（实验性）」。")
        self._fill_model_table()
        self._fill_thumbnails()
        self._update_buttons()

    def _clear_thumbnails(self) -> None:
        while self.thumb_grid.count():
            item = self.thumb_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _fill_model_table(self) -> None:
        self.model_table.setRowCount(0)
        if self.model is None:
            return
        self.model_table.setRowCount(len(self.model.centers))
        for j, center in enumerate(self.model.centers):
            values = [f"Φ{j}", str(self.model.support[j]), str(len(center))]
            for c, text in enumerate(values):
                self.model_table.setItem(j, c, QTableWidgetItem(text))

    def _fill_thumbnails(self) -> None:
        self._clear_thumbnails()
        if self.model is None:
            return
        shown = self.model.centers[:12]
        for j, center in enumerate(shown):
            w = pg.PlotWidget()
            w.setBackground("w")
            w.setFixedHeight(140)
            w.showGrid(x=True, y=True, alpha=0.12)
            w.getPlotItem().setTitle(f"Φ{j}  n={self.model.support[j]}", size="8pt")
            w.plot(np.asarray(center)[:, 0], np.asarray(center)[:, 1],
                   pen=pg.mkPen(COLORS[j % len(COLORS)], width=1.6))
            self.thumb_grid.addWidget(w, j // 4, j % 4)
        if len(self.model.centers) > len(shown):
            lab = QLabel(f"其余 {len(self.model.centers) - len(shown)} 个中心未显示")
            lab.setStyleSheet("color:#57606a;")
            self.thumb_grid.addWidget(lab, len(shown) // 4 + 1, 0, 1, 4)

    def _save_model(self) -> None:
        if self.model is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "保存形状词表", "shape_vocab.json", "JSON (*.json)")
        if not path:
            return
        try:
            self.model.save(path)
            self._set_status(f"词表已保存：{path}")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "指纹研究", f"{type(exc).__name__}: {exc}")

    def _load_model(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "加载形状词表", "", "JSON (*.json)")
        if not path:
            return
        try:
            model = ShapeModel.load(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "指纹研究", f"{type(exc).__name__}: {exc}")
            return
        if model.method != self.method.id:
            QMessageBox.warning(
                self, "指纹研究",
                f"该词表的方法为 {model.method!r}，当前工作区是 {self.method.id!r}。")
        self._on_model(model)
        self._set_status(f"词表已加载：{path}")

    def _decode(self) -> None:
        if self.corpus is None or self.model is None:
            return
        idx = self.event_combo.currentData()
        if idx is None or not (0 <= int(idx) < self.corpus.n_events):
            return
        try:
            desc = self.method.decode(self.corpus.views[int(idx)], self.model)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "指纹研究", f"{type(exc).__name__}: {exc}")
            return
        self._draw_decode(desc)
        self.decode_label.setText(
            f"模型 {self.model.model_id} · {len(desc.segments)} 个片段 · "
            f"接受 {int(desc.features.get('n_accepted', 0))} · "
            f"中位距离 {desc.features.get('median_distance', float('nan')):.4g}")
        self.decode_table.setRowCount(len(desc.segments))
        for i, seg in enumerate(desc.segments):
            values = [
                str(i + 1),
                f"{seg.start / self.corpus.views[int(idx)].fs * 1000:.3f}",
                f"{seg.end / self.corpus.views[int(idx)].fs * 1000:.3f}",
                f"{seg.width_samples / self.corpus.views[int(idx)].fs * 1000:.3f}",
                str(seg.attrs.get("shape_id")),
                f"{seg.attrs.get('distance', float('nan')):.4g}",
                "是" if seg.attrs.get("accepted") else "否",
            ]
            for c, text in enumerate(values):
                self.decode_table.setItem(i, c, QTableWidgetItem(text))

    def _draw_decode(self, desc) -> None:
        view = self.corpus.views[int(self.event_combo.currentData())]
        self.decode_plot.clear()
        body = np.asarray(view.body, dtype=float)
        t = np.arange(body.size) / view.fs * 1000.0
        self.decode_plot.plot(t, body, pen=pg.mkPen("#222222", width=1.0))
        if body.size == 0:
            return
        top = float(np.nanmax(body))
        for seg in desc.segments:
            sid = int(seg.attrs.get("shape_id", 0))
            color = COLORS[sid % len(COLORS)]
            x0 = seg.start / view.fs * 1000.0
            x1 = seg.end / view.fs * 1000.0
            region = pg.LinearRegionItem(values=(x0, x1), movable=False,
                                         brush=pg.mkBrush(color + "33"))
            region.setZValue(-10)
            self.decode_plot.addItem(region)
            line = pg.InfiniteLine(pos=x0, angle=90,
                                   pen=pg.mkPen(color, width=1.0,
                                                style=Qt.DashLine))
            self.decode_plot.addItem(line)
            text = pg.TextItem(f"Φ{sid}", color=color, anchor=(0.5, 1.0))
            text.setPos((x0 + x1) / 2.0, top)
            self.decode_plot.addItem(text)
        self.decode_plot.setXRange(float(t[0]), float(t[-1]), padding=0.02)

    def closeEvent(self, event) -> None:      # noqa: N802 — Qt signature
        for worker in (self._corpus_worker, self._fit_worker):
            if worker is not None and worker.isRunning():
                worker.wait(2000)
        super().closeEvent(event)
