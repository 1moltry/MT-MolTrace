"""Global interval helpers and the annotation-evaluation adapter.

A description stores segment coordinates relative to its event and (since
schema 1.1) also in global samples. Everything downstream — annotation
comparison, interval F1, boundary displacement — needs only the global pairs,
so this module is the single Qt-free, pandas-free bridge between the
description layer and an annotation table.

Coordinates are **global sample indices** and intervals are half-open
``[start, end)``. Tolerance arguments are in milliseconds and converted with
``fs``; matching is the same greedy one-to-one rule used by the sugar
project's annotation evaluator, so its published numbers stay comparable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping

import numpy as np


def to_global_intervals(desc) -> list[tuple[int, int]]:
    """Return a description's segments as sorted global ``(start, end)`` pairs."""
    base = getattr(desc, "event_start", None)
    base = 0 if base is None else int(base)
    out: list[tuple[int, int]] = []
    for seg in getattr(desc, "segments", None) or []:
        s = getattr(seg, "start_global", None)
        e = getattr(seg, "end_global", None)
        if s is None:
            s = base + int(seg.start)
        if e is None:
            e = base + int(seg.end)
        if int(e) > int(s):
            out.append((int(s), int(e)))
    return sorted(out)


def to_global_intervals_by_event(descs: Iterable) -> dict[int, list[tuple[int, int]]]:
    """``{event_id: [(start, end), ...]}`` for a list of descriptions."""
    return {int(d.event_id): to_global_intervals(d) for d in descs}


def match_intervals(preds: list[tuple[int, int]], truths: list[tuple[int, int]],
                    tol_samp: float) -> list[tuple[int, int, float, float]]:
    """Greedy pair-boundary match: both start and end within ``tol_samp``.

    Returns ``[(pred_index, truth_index, d_start, d_end), ...]``. Each side is
    used at most once; candidates are consumed by smallest total displacement.
    """
    cand: list[tuple[int, int, float, float]] = []
    for ip, (ps, pe) in enumerate(preds):
        for it, (ts, te) in enumerate(truths):
            ds, de = abs(ps - ts), abs(pe - te)
            if ds <= tol_samp and de <= tol_samp:
                cand.append((ip, it, float(ds), float(de)))
    cand.sort(key=lambda t: t[2] + t[3])
    used_p: set[int] = set()
    used_t: set[int] = set()
    out: list[tuple[int, int, float, float]] = []
    for ip, it, ds, de in cand:
        if ip in used_p or it in used_t:
            continue
        used_p.add(ip)
        used_t.add(it)
        out.append((ip, it, ds, de))
    return out


def interval_f1(preds: list[tuple[int, int]], truths: list[tuple[int, int]],
                tol_samp: float) -> tuple[float, float, float, int]:
    """Interval-level F1 / precision / recall / matched count."""
    if not preds and not truths:
        return 1.0, 1.0, 1.0, 0
    if not preds or not truths:
        return 0.0, 0.0, 0.0, 0
    m = len(match_intervals(preds, truths, tol_samp))
    prec = m / len(preds)
    rec = m / len(truths)
    f1 = 0.0 if (prec + rec) == 0 else 2 * prec * rec / (prec + rec)
    return f1, prec, rec, m


@dataclass
class IntervalEval:
    """Aggregated interval evaluation over a set of events."""

    fs: float
    tols_ms: tuple[float, ...] = (0.25, 0.5, 1.0)
    n_events: int = 0
    n_pred: int = 0
    n_truth: int = 0
    #: {tolerance_ms: (f1, precision, recall, matched)}
    interval_f1: dict[float, tuple[float, float, float, int]] = field(default_factory=dict)
    disp_start_ms: list[float] = field(default_factory=list)
    disp_end_ms: list[float] = field(default_factory=list)
    missed_width_ms: list[float] = field(default_factory=list)
    spurious_width_ms: list[float] = field(default_factory=list)

    def main_tol(self) -> float:
        for t in (0.5, 1.0, 0.25):
            if t in self.tols_ms:
                return t
        return self.tols_ms[len(self.tols_ms) // 2]

    def median_displacement_ms(self) -> tuple[float, float]:
        ds = np.asarray(self.disp_start_ms, dtype=float)
        de = np.asarray(self.disp_end_ms, dtype=float)
        return (float(np.median(ds)) if ds.size else float("nan"),
                float(np.median(de)) if de.size else float("nan"))

    def summary(self) -> dict:
        main = self.main_tol()
        f1, prec, rec, matched = self.interval_f1.get(main, (float("nan"),) * 4)
        ms, me = self.median_displacement_ms()
        return {
            "n_events": self.n_events,
            "n_pred": self.n_pred,
            "n_truth": self.n_truth,
            f"interval_F1@{main}ms": f1,
            f"interval_precision@{main}ms": prec,
            f"interval_recall@{main}ms": rec,
            "median_disp_start_ms": ms,
            "median_disp_end_ms": me,
            "n_missed": self.n_truth - matched,
            "n_spurious": self.n_pred - matched,
        }


def evaluate_intervals(preds_by_event: Mapping[int, list[tuple[int, int]]],
                       truths_by_event: Mapping[int, list[tuple[int, int]]],
                       fs: float, *, tols_ms=(0.25, 0.5, 1.0),
                       disp_tol_ms: float = 2.0) -> IntervalEval:
    """Compare predicted global intervals with reference intervals per event."""
    fs = float(fs)
    tols = tuple(float(t) for t in tols_ms)
    rep = IntervalEval(fs=fs, tols_ms=tols)
    common = sorted(set(preds_by_event) & set(truths_by_event))
    rep.n_events = len(common)

    tol_samp = {t: t / 1000.0 * fs for t in tols}
    disp_tol_samp = disp_tol_ms / 1000.0 * fs
    counts = {t: [0, 0, 0] for t in tols}   # matched, n_pred, n_truth
    main = rep.main_tol()

    for ev in common:
        p_iv = sorted(preds_by_event[ev])
        t_iv = sorted(truths_by_event[ev])

        for t in tols:
            _, _, _, m = interval_f1(p_iv, t_iv, tol_samp[t])
            counts[t][0] += m
            counts[t][1] += len(p_iv)
            counts[t][2] += len(t_iv)

        matched_pairs = match_intervals(p_iv, t_iv, disp_tol_samp)
        for _ip, _it, ds, de in matched_pairs:
            rep.disp_start_ms.append(ds / fs * 1000.0)
            rep.disp_end_ms.append(de / fs * 1000.0)

        main_matches = match_intervals(p_iv, t_iv, tol_samp[main])
        matched_t = {it for _, it, _, _ in main_matches}
        matched_p = {ip for ip, _, _, _ in main_matches}
        for it, (s, e) in enumerate(t_iv):
            if it not in matched_t:
                rep.missed_width_ms.append((e - s) / fs * 1000.0)
        for ip, (s, e) in enumerate(p_iv):
            if ip not in matched_p:
                rep.spurious_width_ms.append((e - s) / fs * 1000.0)

    rep.n_pred = sum(len(v) for v in preds_by_event.values())
    rep.n_truth = sum(len(v) for v in truths_by_event.values())
    for t in tols:
        m, npred, ntrue = counts[t]
        if npred == 0 and ntrue == 0:
            rep.interval_f1[t] = (1.0, 1.0, 1.0, 0)
        elif npred == 0 or ntrue == 0:
            rep.interval_f1[t] = (0.0, 0.0, 0.0, m)
        else:
            prec, rec = m / npred, m / ntrue
            f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
            rep.interval_f1[t] = (f1, prec, rec, m)
    return rep
