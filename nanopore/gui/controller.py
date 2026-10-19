"""App state + background analysis worker.

Reuses :func:`nanopore.analyze.analyze` (base pipeline + enabled mods) in a
worker thread so a large .abf never blocks the Qt event loop.
"""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import QObject, QThread, pyqtSignal

from ..analyze import analyze
from ..config import PipelineConfig
from ..io import read_abf
from .bus import bus


class AnalysisWorker(QThread):
    done = pyqtSignal(object, object, object, object, object)   # rec, lv, df, df_excluded, (anom, det)
    failed = pyqtSignal(str)

    def __init__(self, path: str | Path, cfg: PipelineConfig):
        super().__init__()
        self.path = Path(path)
        self.cfg = cfg

    def run(self) -> None:
        try:
            rec = read_abf(self.path)
            res = analyze(rec, self.cfg)
            self.done.emit(res.rec, res.lv, res.df, res.df_excluded, (res.anom, res.det))
        except Exception as exc:  # surface as a status message, keep the app alive
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class RoiWorker(QThread):
    """Segment-local (Cursor) analysis for a user-selected region."""
    done = pyqtSignal(object, tuple)   # roi df, (start_s, end_s)
    failed = pyqtSignal(str)

    def __init__(self, rec, cfg, start_s: float, end_s: float):
        super().__init__()
        self.rec = rec
        self.cfg = cfg
        self.start_s = start_s
        self.end_s = end_s

    def run(self) -> None:
        try:
            from ..roi import analyze_roi

            df, _det, _lv = analyze_roi(
                self.rec.current, self.rec.sample_rate_hz,
                self.start_s, self.end_s, self.cfg,
            )
            self.done.emit(df, (self.start_s, self.end_s))
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class Controller(QObject):
    """Holds the currently loaded recording + analysis results."""

    def __init__(self) -> None:
        super().__init__()
        self.rec = None
        self.lv = None
        self.df = None
        self.df_excluded = None
        self.anom = None
        self.det = None
        self.cfg: PipelineConfig = PipelineConfig()
        self._worker: AnalysisWorker | None = None
        self._workers: list[AnalysisWorker] = []   # keep refs until finished
        self._gen = 0                              # stale-result guard
        self._running = False
        self._pending = False                      # rerun requested mid-run
        self._roi_worker: RoiWorker | None = None
        self.roi_df = None
        self.roi_span = None

    def load(self, path: str | Path, cfg: PipelineConfig | None = None) -> None:
        if cfg is not None:
            self.cfg = cfg
        self._gen += 1           # invalidate any in-flight result for the old file
        self._pending = False
        self._start(path)

    def set_config(self, cfg: PipelineConfig) -> None:
        self.cfg = cfg

    def rerun(self) -> None:
        """Re-analyse the current file; requests during a run coalesce into one."""
        if self.rec is None:
            return
        if self._running:
            self._pending = True
            return
        self._start(self.rec.path)

    def rerun_roi(self, start_s: float, end_s: float) -> None:
        """Analyse a user-selected region independently (Cursor semantics)."""
        if self.rec is None:
            bus.status.emit("请先打开一个 .abf 文件")
            return
        self._roi_worker = RoiWorker(self.rec, self.cfg, start_s, end_s)
        self._roi_worker.done.connect(self._on_roi_done)
        self._roi_worker.failed.connect(self._on_failed)
        bus.status.emit(f"ROI 分析 [{start_s:.2f}, {end_s:.2f}]s …")
        self._roi_worker.start()

    def _on_roi_done(self, df, span) -> None:
        self.roi_df = df
        self.roi_span = span
        n = 0 if df is None else len(df)
        bus.status.emit(f"ROI [{span[0]:.2f}, {span[1]:.2f}]s: {n} 事件")
        bus.roi_finished.emit(df, span)

    def _start(self, path: str | Path) -> None:
        self._gen += 1
        gen = self._gen
        self._running = True
        worker = AnalysisWorker(path, self.cfg)
        self._worker = worker
        self._workers.append(worker)
        worker.done.connect(
            lambda rec, lv, df, dx, ad, g=gen: self._on_done(rec, lv, df, dx, ad, g))
        worker.failed.connect(lambda msg, g=gen: self._on_failed(msg, g))
        worker.finished.connect(lambda w=worker: self._release(w))
        bus.status.emit(f"分析中: {Path(path).name} …")
        worker.start()

    def _release(self, worker) -> None:
        if worker in self._workers:
            self._workers.remove(worker)

    def _after_run(self, gen: int) -> None:
        if gen != self._gen:
            return                       # a newer run owns the state
        self._running = False
        if self._pending:
            self._pending = False
            if self.rec is not None:
                self._start(self.rec.path)

    def _on_done(self, rec, lv, df, df_excluded, anom_det, gen: int) -> None:
        if gen != self._gen:
            return                       # superseded by a newer run
        self.rec, self.lv, self.df = rec, lv, df
        self.df_excluded = df_excluded
        self.anom, self.det = anom_det
        n_removed = len(df_excluded) if df_excluded is not None else 0
        mode = getattr(self.cfg, "event_mode", "level")
        bus.status.emit(f"完成[{mode}]: {rec.path.name}\t保留 {len(df)} / 剔除 {n_removed}（明细见异常面板）")
        bus.file_loaded.emit(str(rec.path))
        bus.detection_finished.emit()
        self._after_run(gen)

    def _on_failed(self, msg: str, gen: int) -> None:
        if gen == self._gen:
            bus.status.emit(f"错误: {msg}")
        self._after_run(gen)


controller = Controller()
