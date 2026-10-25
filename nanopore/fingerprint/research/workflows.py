"""Shared research workflows used by the CLI and the GUI.

Keep the orchestration here so the command line and the desktop dialog run the
same corpus construction, fitting and writing code.
"""
from __future__ import annotations

from pathlib import Path

from ..registry import get_describer
from .corpus import EventCorpus
from .model import ShapeModel


def build_corpus(paths, cfg, *, limit: int | None = None,
                 progress=None, cancel=None) -> EventCorpus:
    """Analyse files and collect their kept events into a corpus."""
    return EventCorpus.from_files(paths, cfg, limit=limit,
                                  progress=progress, cancel=cancel)


def fit_vocabulary(corpus: EventCorpus, params: dict | None = None,
                   method_id: str = "shape_vocab") -> ShapeModel:
    """Fit a vocabulary with a registered ``CorpusShapeMethod``."""
    method = get_describer(method_id)
    return method.fit(corpus, params)


def decode_corpus(corpus: EventCorpus, model: ShapeModel,
                  params: dict | None = None,
                  method_id: str = "shape_vocab") -> list:
    """Decode every view in ``corpus`` with ``model``."""
    method = get_describer(method_id)
    return [method.decode(view, model, params) for view in corpus.views]


def decode_files(paths, cfg, model: ShapeModel, *, limit: int | None = None,
                 params: dict | None = None, method_id: str = "shape_vocab",
                 progress=None, cancel=None) -> tuple[EventCorpus, list]:
    """Convenience: build a corpus from files and decode it."""
    corpus = build_corpus(paths, cfg, limit=limit, progress=progress,
                          cancel=cancel)
    return corpus, decode_corpus(corpus, model, params, method_id=method_id)


def write_decoded_by_source(corpus: EventCorpus, descs: list,
                            out_dir: str | Path) -> list[dict]:
    """Write one ``<stem>_shape_decode_fingerprints.*`` pair per source.

    Reuses the production fingerprint writer, so the shape-decoding output has
    the same columns and provenance fields as a normal fingerprint export.
    """
    from ...analysis import write_fingerprints

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    groups: dict[str, list[int]] = {}
    for i, src in enumerate(corpus.sources):
        groups.setdefault(src, []).append(i)

    written: list[dict] = []
    for source, indices in groups.items():
        views = [corpus.views[i] for i in indices]
        sub = [descs[i] for i in indices]
        if not views:
            continue
        first = views[0]
        stem = Path(source).stem
        paths = write_fingerprints(
            sub, out, f"{stem}_shape_decode",
            fs=float(first.fs), source=source,
            source_id=str(first.source_id),
        )
        written.append({"source": source, **{k: str(v) for k, v in paths.items()}})
    return written
