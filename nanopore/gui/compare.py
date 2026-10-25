"""Algorithm-comparison dialog.

One file, two or three detectors, one screen:
- a metrics table (raw/kept events, dwell, depth, runtime, agreement vs baseline);
- an event-boundary scatter over the downsampled trace, one colour per detector;
- "用此算法查看" hands the choice back to the analysis window / home.

The comparison is intentionally read-only: it never writes event tables.
"""

from __future__ import annotations

import csv
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
import pyqtgraph as pg
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (QCheckBox, QDialog, QFileDialog, QHBoxLayout,
                             QLabel, QLineEdit, QMessageBox, QPushButton,
                             QSplitter, QTableWidget, QTableWidgetItem,
                             QVBoxLayout)

from ..analyze import analyze
from ..compare import boundary_metrics, describer_metrics
from ..config import PipelineConfig
from ..fingerprint import describe_meta, describe_result
from ..io import read_abf
from ..mods import resolve_mods
from ..registry import list_detectors, normalize_config

ALGOS = tuple((spec.id, spec.label) for spec in list_detectors())
_COLORS = {
    "level": (31, 119, 180),
    "burst": (255, 127, 14),
    "plateau": (44, 160, 44),
}
_LABELS = dict(ALGOS)


def _downsample(x: np.ndarray, fs: float, max_points: int = 6000):
    n = len(x)
    if n <= max_points:
        return np.arange(n) / fs, np.asarray(x, dtype=float)
    step = max(1, n // max_points)
    m = (n // step) * step
    y = np.asarray(x[:m], dtype=float).reshape(-1, step).mean(axis=1)
    t = (np.arange(y.size) * step) / fs
    return t, y


class CompareWorker(QThread):
    one = pyqtSignal(str, object)       # detector id, result dict
    failed = pyqtSignal(str)
    done = pyqtSignal()

    def __init__(self, path: str, cfg: PipelineConfig, detectors: list[str]):
        super().__init__()
        self.path = path
        self.cfg = cfg
        self.detectors = detectors

    def run(self) -> None:
        try:
            rec = read_abf(self.path)
            for det in self.detectors:
                cfg = normalize_config(replace(
                    self.cfg, detector=det, enabled_mods=(), event_mode="level"))
                t0 = time.perf_counter()
                res = analyze(rec, cfg)
                elapsed = time.perf_counter() - t0
                kept = ([(float(r.t1), float(r.t2)) for _, r in res.df.iterrows()]
                        if len(res.df) else [])
                raw = [(e.start_s, e.end_s) for e in res.det.events]
                dwell = float(np.median([b - a for a, b in kept])) * 1e3 if kept else float("nan")
                depth = (float(np.median([float(r["mean"]) for _, r in res.df.iterrows()]))
                         if len(res.df) else float("nan"))
                self.one.emit(det, {
                    "kept": kept,
                    "raw": raw,
                    "n_kept": len(kept),
                    "n_raw": len(raw),
                    "dwell_ms": dwell,
                    "depth_pA": depth,
                    "elapsed_s": elapsed,
                    "trace": _downsample(rec.current, rec.sample_rate_hz),
                })
            self.done.emit()
        except Exception as exc:            # noqa: BLE001 — keep the dialog alive
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class CompareDialog(QDialog):
    use_detector = pyqtSignal(str)            # analysis window: switch + rerun
    open_requested = pyqtSignal(str, str)     # home: open file with detector

    def __init__(self, current_path: str | None = None,
                 cfg: PipelineConfig | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("算法对比")
        self.resize(1180, 760)
        self._cfg = cfg or PipelineConfig()
        self._path = current_path or ""
        self._worker: CompareWorker | None = None
        self._results: dict[str, dict] = {}
        self._trace = None

        # --- top: file + algorithms + run ---
        self.file_edit = QLineEdit(self._path)
        self.file_edit.setPlaceholderText("选择要对比的 .abf 文件")
        btn_file = QPushButton("选择文件…")
        btn_file.clicked.connect(self._pick_file)
        row_file = QHBoxLayout()
        row_file.addWidget(QLabel("文件"))
        row_file.addWidget(self.file_edit, 1)
        row_file.addWidget(btn_file)

        self.checks: dict[str, QCheckBox] = {}
        row_algos = QHBoxLayout()
        row_algos.addWidget(QLabel("对比算法"))
        for det, label in ALGOS:
            cb = QCheckBox(label)
            cb.setChecked(True)
            cb.stateChanged.connect(self._on_algo_toggled)
            self.checks[det] = cb
            row_algos.addWidget(cb)
        row_algos.addStretch(1)
        self.btn_params = QPushButton("编辑参数…")
        self.btn_params.clicked.connect(self._edit_params)
        row_algos.addWidget(self.btn_params)
        self.btn_run = QPushButton("开始对比")
        self.btn_run.clicked.connect(self._run)
        row_algos.addWidget(self.btn_run)

        # --- centre: trace + boundary markers, then metrics table ---
        self.plot = pg.PlotWidget()
        self.plot.setBackground("w")
        self.plot.showGrid(x=True, y=True, alpha=0.15)
        self.plot.setLabel("bottom", "时间", units="s")
        self.plot.setLabel("left", "电流", units="pA")
        self.plot.addLegend(offset=(-10, 10))
        self._markers: dict[str, list] = {}

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels([
            "算法", "原始事件", "保留事件", "中位驻留 (ms)", "中位深度 (pA)",
            "用时 (s)", "与基准匹配", "仅此处有", "中位边界差 (ms)",
        ])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)

        split = QSplitter(Qt.Vertical)
        split.addWidget(self.plot)
        split.addWidget(self.table)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)

        # --- bottom actions ---
        self.status = QLabel("选择 2–3 种算法，点“开始对比”。")
        self.status.setStyleSheet("color:#57606a;")
        btn_export = QPushButton("导出对比表…")
        btn_export.clicked.connect(self._export)
        btn_desc = QPushButton("描述器指标…")
        btn_desc.clicked.connect(self._describer_metrics)
        self.btn_use = QPushButton("用选中算法查看")
        self.btn_use.clicked.connect(self._use_selected)
        self.btn_use.setEnabled(False)
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.reject)
        actions = QHBoxLayout()
        actions.addWidget(self.status, 1)
        actions.addWidget(btn_export)
        actions.addWidget(btn_desc)
        actions.addWidget(self.btn_use)
        actions.addWidget(btn_close)

        lay = QVBoxLayout(self)
        lay.addLayout(row_file)
        lay.addLayout(row_algos)
        lay.addWidget(split, 1)
        lay.addLayout(actions)

    # ---------------------------------------------------------------- setup
    def _pick_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择 .abf", "", "ABF (*.abf)")
        if path:
            self.file_edit.setText(path)

    def _edit_params(self) -> None:
        from .parampanel import ParamDialog

        dlg = ParamDialog(self._cfg, self)
        if dlg.exec_():
            self._cfg = dlg.config()
            self.status.setText("参数已更新；点“开始对比”重新运行。")

    def _selected(self) -> list[str]:
        return [det for det, _ in ALGOS if self.checks[det].isChecked()]

    def _on_algo_toggled(self, *_args) -> None:
        self.btn_use.setEnabled(False)

    def _run(self) -> None:
        path = self.file_edit.text().strip()
        if not Path(path).is_file():
            QMessageBox.warning(self, "算法对比", "请先选择一个存在的 .abf 文件。")
            return
        detectors = self._selected()
        if len(detectors) < 2:
            QMessageBox.warning(self, "算法对比", "至少选择两种算法。")
            return
        self._results.clear()
        self.table.setRowCount(0)
        self.plot.clear()
        self.plot.addLegend(offset=(-10, 10))
        self._markers.clear()
        self.status.setText("正在分析 …")
        self.btn_run.setEnabled(False)
        self.btn_use.setEnabled(False)
        self._worker = CompareWorker(path, self._cfg, detectors)
        self._worker.one.connect(self._on_one)
        self._worker.failed.connect(self._on_failed)
        self._worker.done.connect(self._on_done)
        self._worker.start()

    # ------------------------------------------------------------ results
    def _on_one(self, det: str, result: dict) -> None:
        self._results[det] = result
        if self._trace is None:
            self._trace = result["trace"]
            t, y = self._trace
            self.plot.plot(t, y, pen=pg.mkPen((80, 80, 80), width=1),
                           name="电流")
            self._y_top = float(np.nanmax(y)) if y.size else 0.0
        t, y = result["trace"]
        span = float(np.nanmax(y) - np.nanmin(y)) if y.size else 1.0
        idx = [d for d, _ in ALGOS].index(det)
        y_level = self._y_top + (0.08 + 0.07 * idx) * span
        color = _COLORS[det]
        starts = np.array([a for a, _ in result["kept"]])
        ends = np.array([b for _, b in result["kept"]])
        start_item = pg.ScatterPlotItem(
            starts, np.full(starts.size, y_level), symbol="t", size=7,
            brush=pg.mkBrush(color), pen=None,
            name=f"{_LABELS[det]} 起点")
        end_item = pg.ScatterPlotItem(
            ends, np.full(ends.size, y_level + 0.035 * span), symbol="s", size=5,
            brush=pg.mkBrush(color), pen=None,
            name=f"{_LABELS[det]} 终点")
        self.plot.addItem(start_item)
        self.plot.addItem(end_item)
        self._markers[det] = [start_item, end_item]
        self._refresh_table()

    def _on_failed(self, message: str) -> None:
        self.status.setText("失败：" + message)
        self.btn_run.setEnabled(True)

    def _on_done(self) -> None:
        self.status.setText(
            f"完成：{len(self._results)} 种算法；点表格行后可选“用选中算法查看”。")
        self.btn_run.setEnabled(True)
        self.btn_use.setEnabled(bool(self._results))
        self._refresh_table()

    def _baseline(self) -> str | None:
        for det, _ in ALGOS:
            if det in self._results:
                return det
        return None

    def _refresh_table(self) -> None:
        base = self._baseline()
        rows = [det for det, _ in ALGOS if det in self._results]
        self.table.setRowCount(len(rows))
        for r, det in enumerate(rows):
            res = self._results[det]
            if base and det != base:
                m = boundary_metrics(self._results[base]["kept"], res["kept"])
                matched, only, diff = m["matched"], m["only_other"], m["d_boundary_ms"]
            else:
                matched, only, diff = "—", "—", "—"
            values = [
                _LABELS[det],
                str(res["n_raw"]),
                str(res["n_kept"]),
                f"{res['dwell_ms']:.1f}" if np.isfinite(res["dwell_ms"]) else "—",
                f"{res['depth_pA']:.1f}" if np.isfinite(res["depth_pA"]) else "—",
                f"{res['elapsed_s']:.1f}",
                str(matched),
                str(only),
                f"{diff:.2f}" if isinstance(diff, float) and np.isfinite(diff) else diff,
            ]
            for c, text in enumerate(values):
                self.table.setItem(r, c, QTableWidgetItem(text))

    # ------------------------------------------------------------- actions
    def _selected_detector(self) -> str | None:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if rows:
            det = [d for d, _ in ALGOS if d in self._results][rows[0].row()]
            return det
        base = self._baseline()
        return base

    def _use_selected(self) -> None:
        det = self._selected_detector()
        if not det:
            return
        path = self.file_edit.text().strip()
        self.use_detector.emit(det)
        if not self.parent() or not getattr(self.parent(), "params", None):
            self.open_requested.emit(path, det)
        self.accept()

    def _export(self) -> None:
        if not self._results:
            QMessageBox.information(self, "算法对比", "还没有对比结果。")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出对比表", "algorithm_comparison.csv", "CSV (*.csv)")
        if not path:
            return
        base = self._baseline()
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["algorithm", "n_raw", "n_kept", "median_dwell_ms",
                        "median_depth_pA", "elapsed_s", "matched_vs_baseline",
                        "only_here", "median_boundary_diff_ms"])
            for det, res in self._results.items():
                if base and det != base:
                    m = boundary_metrics(self._results[base]["kept"], res["kept"])
                    matched, only, diff = m["matched"], m["only_other"], m["d_boundary_ms"]
                else:
                    matched, only, diff = "", "", ""
                w.writerow([det, res["n_raw"], res["n_kept"],
                            f"{res['dwell_ms']:.3f}",
                            f"{res['depth_pA']:.3f}",
                            f"{res['elapsed_s']:.3f}",
                            matched, only,
                            f"{diff:.3f}" if isinstance(diff, float) else ""])
        self.status.setText(f"对比表已导出：{path}")

    def _describer_metrics(self) -> None:
        path = self.file_edit.text().strip()
        if not Path(path).is_file():
            QMessageBox.warning(self, "描述器指标", "请先选择一个存在的 .abf 文件。")
            return
        dlg = DescriberMetricsDialog(path, self._cfg, self)
        dlg.exec_()

    def closeEvent(self, event) -> None:      # noqa: N802 — Qt signature
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(2000)
        super().closeEvent(event)


class DescriberMetricsWorker(QThread):
    """Describe one file with several describers and summarise the output."""

    done = pyqtSignal(object)                 # list[DescriberMetrics]
    failed = pyqtSignal(str)

    def __init__(self, path: str, cfg: PipelineConfig, ids: list[str]):
        super().__init__()
        self.path = path
        self.cfg = cfg
        self.ids = ids

    def run(self) -> None:
        try:
            rec = read_abf(self.path)
            cfg = normalize_config(replace(
                self.cfg,
                enabled_mods=resolve_mods(tuple(self.cfg.enabled_mods) + ("describe",)),
            ))
            res = analyze(rec, cfg, with_descriptions=False)
            outputs: dict[str, list] = {}
            elapsed: dict[str, float] = {}
            for did in self.ids:
                t0 = time.perf_counter()
                outputs[did] = describe_result(
                    res, cfg, describer_id=did,
                    params=dict(cfg.describe_params or {}))
                elapsed[did] = time.perf_counter() - t0
            self.done.emit(describer_metrics(outputs, elapsed))
        except Exception as exc:              # noqa: BLE001 — keep the dialog alive
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class DescriberMetricsDialog(QDialog):
    """Side-by-side describer output metrics for one file."""

    HEADERS = ["描述器", "事件", "有效", "中位段数", "总段数",
               "中位覆盖", "用时 (s)"]

    def __init__(self, path: str, cfg: PipelineConfig, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("描述器指标")
        self.resize(760, 420)
        self._path = path
        self._cfg = cfg
        self._worker: DescriberMetricsWorker | None = None
        self._rows: list[dict] = []

        self.checks: dict[str, QCheckBox] = {}
        row = QHBoxLayout()
        row.addWidget(QLabel(Path(path).name))
        for info in describe_meta():
            cb = QCheckBox(info["label"])
            cb.setChecked(info["id"] in ("dp_bic", "classic"))
            self.checks[info["id"]] = cb
            row.addWidget(cb)
        row.addStretch(1)

        self.table = QTableWidget(0, len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)

        self.status = QLabel("选择描述器后开始。")
        self.status.setStyleSheet("color:#57606a;")
        self.btn_run = QPushButton("开始")
        self.btn_run.clicked.connect(self._run)
        btn_export = QPushButton("导出 CSV…")
        btn_export.clicked.connect(self._export)
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.reject)
        actions = QHBoxLayout()
        actions.addWidget(self.status, 1)
        actions.addWidget(btn_export)
        actions.addWidget(self.btn_run)
        actions.addWidget(btn_close)

        lay = QVBoxLayout(self)
        lay.addLayout(row)
        lay.addWidget(self.table, 1)
        lay.addLayout(actions)

    def _selected(self) -> list[str]:
        return [did for did, cb in self.checks.items() if cb.isChecked()]

    def _run(self) -> None:
        ids = self._selected()
        if not ids:
            self.status.setText("至少选择一个描述器。")
            return
        self.btn_run.setEnabled(False)
        self.status.setText("正在计算 …")
        self._worker = DescriberMetricsWorker(self._path, self._cfg, ids)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_done(self, metrics) -> None:
        self._rows = [m.as_row() for m in metrics]
        self.table.setRowCount(len(self._rows))
        for r, row in enumerate(self._rows):
            values = [
                row["describer"], str(row["n_events"]), str(row["n_valid"]),
                f"{row['median_segments']:.2f}"
                if np.isfinite(row["median_segments"]) else "—",
                str(row["total_segments"]),
                f"{row['median_coverage']:.3f}"
                if np.isfinite(row["median_coverage"]) else "—",
                f"{row['elapsed_s']:.2f}"
                if np.isfinite(row["elapsed_s"]) else "—",
            ]
            for c, text in enumerate(values):
                self.table.setItem(r, c, QTableWidgetItem(text))
        self.btn_run.setEnabled(True)
        self.status.setText(f"完成：{len(self._rows)} 个描述器。")

    def _on_failed(self, message: str) -> None:
        self.btn_run.setEnabled(True)
        self.status.setText("失败：" + message)

    def _export(self) -> None:
        if not self._rows:
            QMessageBox.information(self, "描述器指标", "还没有结果。")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出描述器指标", "describer_metrics.csv", "CSV (*.csv)")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(self._rows[0]))
            writer.writeheader()
            writer.writerows(self._rows)
        self.status.setText(f"已导出：{path}")

    def closeEvent(self, event) -> None:      # noqa: N802 — Qt signature
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(2000)
        super().closeEvent(event)
