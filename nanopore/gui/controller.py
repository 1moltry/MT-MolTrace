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
    done = pyqtSignal(object, object, object, object, object, object)
    # rec, levels, kept df, excluded df, (anomaly, detection), full AnalysisResult
    failed = pyqtSignal(str)

    def __init__(self, path: str | Path, cfg: PipelineConfig):
        super().__init__()
        self.path = Path(path)
        self.cfg = cfg

    def run(self) -> None:
        try:
            rec = read_abf(self.path)
            res = analyze(rec, self.cfg, with_descriptions=False)
            self.done.emit(res.rec, res.lv, res.df, res.df_excluded,
                           (res.anom, res.det), res)
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


class DescribeWorker(QThread):
    """Describe one event on demand (the DP can take ~0.5 s on long events).

    Consumes the ``AnalysisResult`` rather than re-reading the recording, so
    the description uses the same filtered trace, dynamic I0 window and voltage
    trace as detection. Emits the cache key together with the description.
    """

    done = pyqtSignal(object, object)      # cache key tuple, EventDescription
    failed = pyqtSignal(str)

    def __init__(self, analysis, index: int, cfg: PipelineConfig | None = None,
                 describer_id: str | None = None):
        super().__init__()
        self.analysis = analysis
        self.index = int(index)
        self.cfg = cfg
        self.describer_id = describer_id

    def run(self) -> None:
        try:
            from ..fingerprint import cache_key_for, describe_event, get_describer

            describer = get_describer(
                self.describer_id
                or ((getattr(self.cfg, "describer", "") if self.cfg else "") or "dp_bic"))
            params = dict(getattr(self.cfg, "describe_params", {}) or {})
            key = cache_key_for(self.analysis, self.index, describer, params=params)
            desc = describe_event(self.analysis, self.index, describer, params=params)
            self.done.emit(key, desc)
        except Exception as exc:  # noqa: BLE001 — surface as status, keep the app alive
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class ExportDescriptionsWorker(QThread):
    """Describe every kept event and write the fingerprint files.

    Reuses the analysis result and the same writer as the batch pipeline, so a
    single-file export and a batch export carry identical columns.
    """

    progress = pyqtSignal(int, int)
    done = pyqtSignal(object)              # paths dict from write_fingerprints
    failed = pyqtSignal(str)

    def __init__(self, analysis, rec, out_dir: Path, cfg: PipelineConfig):
        super().__init__()
        self.analysis = analysis
        self.rec = rec
        self.out_dir = Path(out_dir)
        self.cfg = cfg
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            from ..analysis import write_fingerprints
            from ..fingerprint import describe_result, source_id_for_rec

            descs = describe_result(
                self.analysis, self.cfg,
                progress=lambda i, n: self.progress.emit(i, n),
                cancel=lambda: self._cancel,
            )
            source = Path(self.rec.path)
            paths = write_fingerprints(
                descs, self.out_dir, source.stem,
                fs=self.rec.sample_rate_hz, source=source.name,
                source_id=source_id_for_rec(self.rec),
            )
            self.done.emit(paths)
        except Exception as exc:  # noqa: BLE001 — surface as status, keep the app alive
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
        self.analysis = None
        self.cfg: PipelineConfig = PipelineConfig()
        self._worker: AnalysisWorker | None = None
        self._workers: list[AnalysisWorker] = []   # keep refs until finished
        self._gen = 0                              # stale-analysis guard
        self._desc_gen = 0                         # stale-description guard
        self._running = False
        self._pending = False                      # rerun requested mid-run
        self._roi_worker: RoiWorker | None = None
        self.roi_df = None
        self.roi_span = None
        self.desc_cache: dict[tuple, object] = {}  # (event_key, describer, version, params, data)
        self._desc_pending: set[tuple] = set()
        self._desc_workers: list[DescribeWorker] = []

    def load(self, path: str | Path, cfg: PipelineConfig | None = None) -> None:
        if cfg is not None:
            self.cfg = cfg
        self._gen += 1           # invalidate any in-flight result for the old file
        self._desc_gen += 1
        self._pending = False
        self._start(path)

    def set_config(self, cfg: PipelineConfig) -> None:
        """Replace the protocol; descriptions from the old protocol are stale."""
        self.cfg = cfg
        self._desc_gen += 1
        self.desc_cache.clear()
        self._desc_pending.clear()

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

    def description_key(self, idx: int, describer_id: str | None = None) -> tuple | None:
        """Cache key for event ``idx`` under a describer and its parameters."""
        if self.analysis is None or self.df is None or not (0 <= idx < len(self.df)):
            return None
        from ..fingerprint import cache_key_for, get_describer

        try:
            describer = get_describer(
                describer_id or self.cfg.describer or "dp_bic")
            return cache_key_for(self.analysis, idx, describer,
                                 params=dict(self.cfg.describe_params or {}))
        except Exception:  # noqa: BLE001 — a bad describer id must not break selection
            return None

    def cached_description(self, idx: int, describer_id: str | None = None):
        key = self.description_key(idx, describer_id)
        return None if key is None else self.desc_cache.get(key)

    def describe_event(self, idx: int, describer_id: str | None = None) -> None:
        """Emit (or compute) the description for the 0-based event ``idx``."""
        if self.rec is None or self.df is None or not (0 <= idx < len(self.df)):
            return
        did = describer_id or self.cfg.describer or "dp_bic"
        if "describe" not in self.cfg.enabled_mods or self.analysis is None:
            bus.description_ready.emit(idx + 1, None, did)
            return
        key = self.description_key(idx, did)
        if key is None:
            bus.status.emit("描述准备失败: 描述器不可用")
            return
        if key in self.desc_cache:
            bus.description_ready.emit(idx + 1, self.desc_cache[key], did)
            return
        if key in self._desc_pending:
            return
        self._desc_pending.add(key)
        gen = self._desc_gen
        worker = DescribeWorker(self.analysis, idx, self.cfg, describer_id=did)
        self._desc_workers.append(worker)
        worker.done.connect(lambda k, desc, g=gen: self._on_described(k, desc, g))
        worker.failed.connect(
            lambda msg, k=key, g=gen: self._on_desc_failed(msg, k, g))
        worker.finished.connect(lambda w=worker: self._release_desc(w))
        worker.start()

    def _on_described(self, key: tuple, desc, gen: int) -> None:
        self._desc_pending.discard(key)
        if gen != self._desc_gen:
            return
        self.desc_cache[key] = desc
        bus.description_ready.emit(getattr(desc, "event_id", 0), desc,
                                   getattr(desc, "describer", ""))

    def _on_desc_failed(self, msg: str, key: tuple, gen: int) -> None:
        self._desc_pending.discard(key)
        if gen == self._desc_gen:
            bus.status.emit(f"描述失败: {msg}")

    def _release_desc(self, worker) -> None:
        if worker in self._desc_workers:
            self._desc_workers.remove(worker)

    def _start(self, path: str | Path) -> None:
        self._gen += 1
        self._desc_gen += 1
        gen = self._gen
        self._running = True
        self.desc_cache.clear()
        self._desc_pending.clear()
        worker = AnalysisWorker(path, self.cfg)
        self._worker = worker
        self._workers.append(worker)
        worker.done.connect(
            lambda rec, lv, df, dx, ad, res, g=gen:
            self._on_done(rec, lv, df, dx, ad, res, g))
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

    def _on_done(self, rec, lv, df, df_excluded, anom_det, analysis, gen: int) -> None:
        if gen != self._gen:
            return                       # superseded by a newer run
        self.rec, self.lv, self.df = rec, lv, df
        self.df_excluded = df_excluded
        self.anom, self.det = anom_det
        self.analysis = analysis
        n_removed = len(df_excluded) if df_excluded is not None else 0
        anomaly = "异常识别：开" if analysis.anomaly_enabled else "异常识别：关"
        bus.status.emit(
            f"完成[{analysis.detector_id}]: {rec.path.name}\t"
            f"保留 {len(df)} / 剔除 {n_removed}"
            f"（检测规则 {analysis.detector_rejected}） · {anomaly}")
        bus.file_loaded.emit(str(rec.path))
        bus.detection_finished.emit()
        self._after_run(gen)

    def _on_failed(self, msg: str, gen: int) -> None:
        if gen == self._gen:
            bus.status.emit(f"错误: {msg}")
        self._after_run(gen)


controller = Controller()
