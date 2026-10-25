"""Cross-event corpus for experimental shape discovery.

An :class:`EventCorpus` is a flat list of :class:`~nanopore.fingerprint.EventView`
objects plus one source name per view. It is the only input a
:class:`CorpusShapeMethod` may fit on; it never re-reads an ABF after it is
built.

The corpus deliberately keeps event identity and source names, so leave-one-
file reproduction and manual overlay checks can be run later without changing
the representation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..context import build_event_view


@dataclass
class EventCorpus:
    views: list
    sources: list[str]
    meta: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if len(self.views) != len(self.sources):
            raise ValueError("views and sources must have the same length")

    @property
    def n_events(self) -> int:
        return len(self.views)

    def source_names(self) -> list[str]:
        return sorted(set(self.sources))

    def subset(self, indices) -> "EventCorpus":
        idx = [int(i) for i in indices]
        return EventCorpus([self.views[i] for i in idx],
                           [self.sources[i] for i in idx],
                           dict(self.meta))

    def body_meta(self) -> list[dict]:
        out = []
        for i, (v, src) in enumerate(zip(self.views, self.sources)):
            out.append({
                "index": i,
                "source": src,
                "event_id": v.event_id,
                "event_key": v.event_key,
                "dwell_s": v.duration_ms / 1000.0,
                "depth_pA": float(v.i_blockade - v.i_open),
                "i_open_pA": float(v.i_open),
                "sigma_open_pA": float(v.sigma_open),
                "body_samples": int(v.n_samples),
            })
        return out

    @classmethod
    def from_analysis(cls, result, *, source_name: str | None = None,
                      indices=None, max_events: int | None = None
                      ) -> "EventCorpus":
        """Build a corpus from an ``AnalysisResult`` (kept events only)."""
        n = len(result.df)
        if indices is None:
            idx = list(range(n))
        else:
            idx = [int(i) for i in indices if 0 <= int(i) < n]
        if max_events is not None:
            idx = idx[:int(max_events)]
        name = source_name or (Path(result.rec.path).name
                               if getattr(result, "rec", None) is not None else "synthetic")
        views = [build_event_view(result, i) for i in idx]
        return cls(views, [name] * len(views),
                   {"kind": "analysis", "source": name,
                    "requested": len(idx)})

    @classmethod
    def from_files(cls, paths, cfg, *, limit: int | None = None,
                   progress=None, cancel=None) -> "EventCorpus":
        """Analyse ``.abf`` files and collect their kept events.

        Detection uses the supplied :class:`~nanopore.config.PipelineConfig`;
        descriptions are not computed here. A bad file is recorded in
        ``meta["errors"]`` and does not abort the rest of the corpus.
        """
        from ...analyze import analyze
        from ...io import read_abf

        files = [Path(p) for p in paths]
        views: list = []
        sources: list[str] = []
        errors: list[str] = []
        for k, path in enumerate(files, start=1):
            if cancel is not None and cancel():
                raise RuntimeError("已取消")
            try:
                rec = read_abf(path)
                res = analyze(rec, cfg, with_descriptions=False, cancel=cancel)
                for i in range(len(res.df)):
                    if limit is not None and len(views) >= int(limit):
                        break
                    views.append(build_event_view(res, i))
                    sources.append(path.name)
                if limit is not None and len(views) >= int(limit):
                    if progress is not None:
                        progress(k, len(files), path.name)
                    break
            except Exception as exc:  # noqa: BLE001 — one bad file is not fatal
                errors.append(f"{path.name}: {type(exc).__name__}: {exc}")
            if progress is not None:
                progress(k, len(files), path.name)
        return cls(views, sources,
                   {"kind": "files", "paths": [str(p) for p in files],
                    "limit": limit, "errors": errors})
