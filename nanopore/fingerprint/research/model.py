"""Shape vocabulary: fit on a corpus, save/load, decode one event.

The vocabulary is the experimental end of phase 7. It is deliberately not a
production describer: ``maturity = "experimental"``, no default enablement, and
every description carries ``quality["experimental"] = True`` plus the recorded
gate result (legacy AUC 0.674 / 0.715, below the planned 0.85).

The model is a plain JSON document: centers are ``(n, 2)`` curves in the R1/R2
representation, with support counts, the clustering threshold and the exact fit
parameters. ``decode`` always uses the model's own fit parameters for the
representation, so a stale parameter in the main panel cannot silently change
the meaning of a center.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from ...params import ParamSpec
from ..contracts import EventDescription, EventView, Segment, params_hash
from ..engine import finalize_description
from ..registry import (CorpusShapeMethod, DescriberUnavailable,
                        EventDescriber, register)
from .corpus import EventCorpus
from .curves import dist
from .deps import require_research
from .fragments import (FragmentParams, cluster_fragments, extract_fragments,
                        extract_fragment_spans)

GATE_NOTE = ("legacy shape vocabulary: AUC 0.674 (N1tele) / 0.715 (N2phase), "
             "below the planned 0.85 gate; treat as an unvalidated baseline")


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, float) and not np.isfinite(value):
        return str(value)
    return value


@dataclass
class ShapeModel:
    """A fitted vocabulary plus everything needed to decode with it."""

    method: str
    version: str
    params: dict
    centers: list[np.ndarray]
    support: list[int]
    threshold: float
    sources: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    schema_version: str = "1"

    @property
    def model_id(self) -> str:
        blob = json.dumps({
            "method": self.method,
            "version": self.version,
            "params": _jsonable(self.params),
            "centers": [np.asarray(c).tolist() for c in self.centers],
            "support": list(self.support),
            "threshold": self.threshold,
        }, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha1(blob.encode()).hexdigest()[:12]

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "method": self.method,
            "version": self.version,
            "params": _jsonable(self.params),
            "centers": [np.asarray(c, dtype=float).tolist() for c in self.centers],
            "support": [int(s) for s in self.support],
            "threshold": float(self.threshold),
            "sources": list(self.sources),
            "metrics": _jsonable(self.metrics),
            "metadata": _jsonable(self.metadata),
            "model_id": self.model_id,
        }

    @classmethod
    def from_dict(cls, data: Mapping) -> "ShapeModel":
        return cls(
            method=str(data.get("method", "")),
            version=str(data.get("version", "1")),
            params=dict(data.get("params") or {}),
            centers=[np.asarray(c, dtype=float)
                     for c in (data.get("centers") or [])],
            support=[int(s) for s in (data.get("support") or [])],
            threshold=float(data.get("threshold", 0.0)),
            sources=[str(s) for s in (data.get("sources") or [])],
            metrics=dict(data.get("metrics") or {}),
            metadata=dict(data.get("metadata") or {}),
            schema_version=str(data.get("schema_version", "1")),
        )

    def save(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=1),
                     encoding="utf-8")
        return p

    @classmethod
    def load(cls, path: str | Path) -> "ShapeModel":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


_ACTIVE_MODELS: dict[str, ShapeModel] = {}


def set_active_model(model: ShapeModel) -> None:
    _ACTIVE_MODELS[str(model.method)] = model


def get_active_model(method_id: str) -> ShapeModel | None:
    return _ACTIVE_MODELS.get(str(method_id))


def clear_active_model(method_id: str | None = None) -> None:
    if method_id is None:
        _ACTIVE_MODELS.clear()
    else:
        _ACTIVE_MODELS.pop(str(method_id), None)


def _fragment_params(p: Mapping) -> FragmentParams:
    return FragmentParams(
        pen_mult=float(p.get("pen_mult", 8.0)),
        smooth_ms=float(p.get("smooth_ms", 0.5)),
        min_frag_ms=float(p.get("min_frag_ms", 0.5)),
        edge_gap_ms=float(p.get("edge_gap_ms", 0.5)),
        mode=str(p.get("mode", "R1")),
        alpha=float(p.get("alpha", 1.0)),
    )


class ShapeVocabularyMethod(CorpusShapeMethod):
    """Fit a variable-length shape vocabulary, then decode events with it."""

    id = "shape_vocab"
    label = "形状词表（实验性）"
    version = "1"
    maturity = "experimental"
    input_trace = "analysis"
    requires_model = True
    data_prerequisites = (
        "跨事件语料（建议至少十几个事件）",
        "事件体开孔电流 i_open 与噪声 σ 有效",
        "片段长度不低于约 0.47 ms 的时间地板",
    )
    params = (
        ParamSpec("pen_mult", 8.0, "float", "PELT 惩罚乘子",
                  "越大切得越少；旧研究默认 8", minimum=0.1, maximum=100.0),
        ParamSpec("smooth_ms", 0.5, "float", "切点前平滑 (ms)",
                  "按时间地板尺度平滑，避免噪声驱动切点", minimum=0.0, maximum=20.0),
        ParamSpec("min_frag_ms", 0.5, "float", "最短片段 (ms)",
                  "短于此的片段丢弃", minimum=0.0, maximum=100.0),
        ParamSpec("edge_gap_ms", 0.5, "float", "边缘剔除窗 (ms)",
                  "触边且该端已近开孔的片段判为过渡沿", minimum=0.0, maximum=20.0),
        ParamSpec("mode", "R1", "choice", "表示",
                  "R1 保留幅度；R2 纯形状对照", choices=("R1", "R2")),
        ParamSpec("alpha", 1.0, "float", "幅度权重 α",
                  "R1 中电流轴的比例；α→0 退化为纯时间形状", minimum=0.0, maximum=10.0),
        ParamSpec("dist", "dtw", "choice", "距离",
                  "DTW 允许时间弯折；Fréchet 是几何真度量",
                  choices=("dtw", "frechet", "euclid")),
        ParamSpec("cap", 1200, "int", "聚类抽样上限",
                  "片段过多时先抽样建簇", minimum=10, maximum=10000),
        ParamSpec("thresh_frac", 0.5, "float", "聚类阈值 (×距离中位)",
                  "越小簇越紧", minimum=0.05, maximum=2.0),
        ParamSpec("min_support", 5, "int", "最小支持度",
                  "低于它的簇不进入词表；全不达标时保留支持度最高的 3 个并标记",
                  minimum=1, maximum=100000),
        ParamSpec("n_iter_dba", 5, "int", "DBA 迭代",
                  "求形状中心的迭代次数", minimum=0, maximum=50),
        ParamSpec("accept_frac", 1.0, "float", "解码接受阈值 (×聚类阈值)",
                  "片段到中心距离超过该比例时标为 unexplained", minimum=0.0, maximum=10.0),
    )

    def fit(self, corpus: EventCorpus,
            params: Mapping[str, Any] | None = None) -> ShapeModel:
        """Fit a vocabulary on a cross-event corpus."""
        require_research()
        p = self.resolve_params(params)
        fp = _fragment_params(p)
        frags = []
        skipped = 0
        for i, view in enumerate(corpus.views):
            try:
                frags.extend(extract_fragments(
                    view.body, view.i_open, view.fs, view.sigma_open,
                    params=fp, event_index=i))
            except ValueError:
                skipped += 1
        if not frags:
            raise ValueError(
                "语料中没有可用片段：检查事件体是否过短，或开孔电流/噪声 σ 是否有效。")

        curves = [f.curve for f in frags]
        _labels, centers, thr = cluster_fragments(
            curves, dist=str(p["dist"]), cap=int(p["cap"]),
            rng=np.random.default_rng(0),
            dist_thresh_frac=float(p["thresh_frac"]),
            n_iter_dba=int(p["n_iter_dba"]))
        if not centers:
            raise ValueError("聚类没有产生形状中心。")

        assign = [int(np.argmin([dist(str(p["dist"]), f, c) for c in centers]))
                  for f in curves]
        support = np.bincount(assign, minlength=len(centers)).astype(int)
        keep = [j for j in range(len(centers))
                if int(support[j]) >= int(p["min_support"])]
        below_min_support = False
        if not keep:
            keep = [int(j) for j in np.argsort(-support)[:min(3, len(centers))]]
            below_min_support = True
        keep = sorted(keep, key=lambda j: -int(support[j]))
        centers = [np.asarray(centers[j], dtype=float) for j in keep]
        support = [int(support[j]) for j in keep]

        model = ShapeModel(
            method=self.id, version=self.version, params=dict(p),
            centers=centers, support=support, threshold=float(thr),
            sources=corpus.source_names(),
            metrics={
                "n_events": int(corpus.n_events),
                "n_fragments": int(len(frags)),
                "n_skipped_events": int(skipped),
                "n_centers": int(len(centers)),
                "threshold": float(thr),
                "support": [int(s) for s in support],
                "below_min_support": bool(below_min_support),
            },
            metadata={
                "experimental": True,
                "gate_note": GATE_NOTE,
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "sources": corpus.source_names(),
                "params": _jsonable(dict(p)),
            },
        )
        set_active_model(model)
        return model

    def decode(self, view: EventView, model: ShapeModel,
               params: Mapping[str, Any] | None = None) -> EventDescription:
        """Apply a fitted vocabulary to one event."""
        require_research()
        if not model.centers:
            raise DescriberUnavailable("形状词表为空：请先拟合或加载一个词表。")
        fp = _fragment_params(model.params)
        try:
            frags = extract_fragments(view.body, view.i_open, view.fs,
                                      view.sigma_open, params=fp)
        except ValueError as exc:
            desc = finalize_description(
                EventDescription(
                    event_id=view.event_id, source=view.source,
                    describer=self.id, describer_version=self.version,
                    params=dict(model.params),
                    quality={"valid": False, "reason": str(exc),
                             "experimental": True, "model_id": model.model_id},
                ),
                view, self, model.params)
            desc.params_hash = params_hash(model.params)
            return desc

        dist_name = str(model.params.get("dist", "dtw"))
        accept_frac = float((params or {}).get(
            "accept_frac", model.params.get("accept_frac", 1.0)))
        segments: list[Segment] = []
        distances: list[float] = []
        n_accepted = 0
        for k, frag in enumerate(frags):
            ds = [dist(dist_name, frag.curve, c) for c in model.centers]
            j = int(np.argmin(ds))
            d = float(ds[j])
            distances.append(d)
            accepted = (model.threshold <= 0
                        or d <= model.threshold * max(accept_frac, 1e-12))
            n_accepted += int(accepted)
            body = view.body
            level = (float(np.median(body[frag.start:frag.end]))
                     if frag.end > frag.start else float("nan"))
            segments.append(Segment(
                start=int(frag.start), end=int(frag.end),
                level_pA=level,
                level_rel=(level - view.i_blockade
                           if np.isfinite(level) else None),
                level_norm=(level / view.i_open
                            if np.isfinite(level) and view.i_open else None),
                attrs={
                    "shape_id": j,
                    "distance": d,
                    "accepted": bool(accepted),
                    "len_ms": (frag.end - frag.start) / view.fs * 1000.0,
                },
                start_global=view.start + int(frag.start),
                end_global=view.start + int(frag.end),
            ))

        covered = sum(seg.width_samples for seg in segments)
        quality = {"valid": True, "experimental": True,
                   "model_id": model.model_id,
                   "n_centers": len(model.centers)}
        if model.metrics.get("below_min_support"):
            quality["below_min_support"] = True
        desc = finalize_description(EventDescription(
            event_id=view.event_id, source=view.source,
            describer=self.id, describer_version=self.version,
            params=dict(model.params), segments=segments,
            features={
                "n_fragments": float(len(segments)),
                "n_accepted": float(n_accepted),
                "median_distance": (float(np.median(distances))
                                    if distances else float("nan")),
                "coverage_frac": covered / max(view.n_samples, 1),
                "n_centers": float(len(model.centers)),
            },
            payload={
                "method": self.id,
                "model_id": model.model_id,
                "n_centers": len(model.centers),
                "threshold": float(model.threshold),
                "params": _jsonable(dict(model.params)),
                "experimental": True,
                "gate_note": GATE_NOTE,
                "shape_ids": [seg.attrs.get("shape_id") for seg in segments],
            },
            quality=quality,
        ), view, self, model.params)
        desc.params_hash = params_hash(model.params)
        return desc

    def describe(self, view: EventView,
                 params: Mapping[str, Any] | None = None) -> EventDescription:
        model = get_active_model(self.id)
        if model is None:
            raise DescriberUnavailable(
                "形状词表尚未拟合：请先在「指纹研究」工作区拟合或加载词表。")
        return self.decode(view, model, params)


class PELTDescriber(EventDescriber):
    """PELT change-point fragments without a vocabulary (experimental)."""

    id = "pelt"
    label = "PELT 变点（实验性）"
    version = "1"
    maturity = "experimental"
    input_trace = "analysis"
    data_prerequisites = (
        "事件体开孔电流 i_open 与噪声 σ 有效",
        "事件体长度不低于约 8 个采样",
        "片段长度不低于约 0.47 ms 的时间地板",
    )
    params = (
        ParamSpec("pen_mult", 8.0, "float", "PELT 惩罚乘子",
                  "越大切得越少；旧研究默认 8", minimum=0.1, maximum=100.0),
        ParamSpec("smooth_ms", 0.5, "float", "切点前平滑 (ms)",
                  "按时间地板尺度平滑", minimum=0.0, maximum=20.0),
        ParamSpec("min_frag_ms", 0.5, "float", "最短片段 (ms)",
                  "短于此的片段丢弃", minimum=0.0, maximum=100.0),
        ParamSpec("edge_gap_ms", 0.5, "float", "边缘剔除窗 (ms)",
                  "触边且该端已近开孔的片段判为过渡沿", minimum=0.0, maximum=20.0),
        ParamSpec("mode", "R1", "choice", "表示",
                  "仅影响内部表示；段电平仍取原始电流中位数",
                  choices=("R1", "R2")),
        ParamSpec("alpha", 1.0, "float", "幅度权重 α",
                  "R1 中电流轴的比例", minimum=0.0, maximum=10.0),
    )

    def describe(self, view: EventView,
                 params: Mapping[str, Any] | None = None) -> EventDescription:
        require_research()
        p = self.resolve_params(params)
        fp = _fragment_params(p)
        try:
            spans = extract_fragment_spans(view.body, view.i_open, view.fs,
                                           view.sigma_open, fp)
        except ValueError as exc:
            return EventDescription(
                event_id=view.event_id, source=view.source,
                describer=self.id, describer_version=self.version,
                params=dict(p),
                quality={"valid": False, "reason": str(exc),
                         "experimental": True},
            )
        segments: list[Segment] = []
        for a, z in spans:
            level = float(np.median(view.body[a:z]))
            segments.append(Segment(
                start=int(a), end=int(z), level_pA=level,
                level_rel=(level - view.i_blockade
                           if np.isfinite(level) else None),
                level_norm=(level / view.i_open
                            if np.isfinite(level) and view.i_open else None),
                attrs={"len_ms": (z - a) / view.fs * 1000.0},
                start_global=view.start + int(a),
                end_global=view.start + int(z),
            ))
        covered = sum(seg.width_samples for seg in segments)
        return EventDescription(
            event_id=view.event_id, source=view.source,
            describer=self.id, describer_version=self.version,
            params=dict(p), segments=segments,
            features={
                "n_fragments": float(len(segments)),
                "coverage_frac": covered / max(view.n_samples, 1),
            },
            payload={"method": self.id, "params": _jsonable(dict(p)),
                     "experimental": True, "gate_note": GATE_NOTE},
            quality={"valid": True, "experimental": True},
        )


register(ShapeVocabularyMethod())
register(PELTDescriber())
