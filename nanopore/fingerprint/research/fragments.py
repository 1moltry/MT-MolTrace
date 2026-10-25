"""PELT change points and variable-length fragment clustering.

Ported from the archived deep-signal project (``work/shape_seg.py``). The
cut is deliberately **loose** (prefer more fragments): fragments are then
grouped by DTW/Fréchet tolerance, so the cluster, not the cut, defines a
shape. PELT uses the ``l2`` cost on the open-pore-normalized body and is
smoothed at the resolution floor first, so noise does not drive breakpoints.

``ruptures`` and ``scikit-learn`` are required only when these functions run;
the dependency guard produces an actionable message instead of a bare
``ImportError``.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .curves import TIME_FLOOR_MS, dba, distance_matrix, represent
from .deps import require, require_research


@dataclass
class FragmentParams:
    pen_mult: float = 8.0
    smooth_ms: float = 0.5
    min_frag_ms: float = 0.5
    edge_gap_ms: float = 0.5
    mode: str = "R1"
    alpha: float = 1.0
    min_size_ms: float = TIME_FLOOR_MS

    def updated(self, values: dict | None = None) -> "FragmentParams":
        out = FragmentParams(**self.__dict__)
        for key, value in (values or {}).items():
            if hasattr(out, key):
                setattr(out, key, value)
        return out


@dataclass
class Fragment:
    """One variable-length fragment inside an event body."""

    start: int                 # sample offset in the event body
    end: int
    curve: np.ndarray          # (n, 2) representation
    event_index: int = -1      # index into the corpus (filled by fit)


def detect_breakpoints(y: np.ndarray, *, min_size: int, pen: float,
                       smooth: int) -> np.ndarray:
    """PELT (l2) breakpoints, with the final index included."""
    from scipy.ndimage import uniform_filter1d

    rpt = require("ruptures")
    ys = uniform_filter1d(np.asarray(y, dtype=float), size=smooth) if smooth > 1 else y
    algo = rpt.Pelt(model="l2", min_size=max(2, int(min_size))).fit(ys)
    return np.asarray(algo.predict(pen=max(float(pen), 1e-12)), dtype=int)


def _fragment_spans(body: np.ndarray, i_open: float, fs: float,
                    sigma_pA: float, p: FragmentParams) -> list[tuple[int, int]]:
    body = np.asarray(body, dtype=float).ravel()
    if body.size < 8:
        return []
    if not np.isfinite(i_open) or float(i_open) == 0.0:
        raise ValueError("i_open is missing or zero")
    if not np.isfinite(sigma_pA) or sigma_pA <= 0:
        raise ValueError("open-pore sigma is missing or non-positive")

    y = body / float(i_open)
    sr = float(sigma_pA) / float(i_open)
    min_size = max(2, int(round(p.min_size_ms * 1e-3 * fs)))
    smooth = max(1, int(round(p.smooth_ms * 1e-3 * fs)))
    pen = float(p.pen_mult) * sr * sr * (smooth if smooth > 1 else 1)
    bounds = detect_breakpoints(y, min_size=min_size, pen=pen, smooth=smooth)
    edges = np.concatenate(([0], bounds))

    min_n = max(2, int(round(p.min_frag_ms * 1e-3 * fs)))
    gap = max(0, int(round(p.edge_gap_ms * 1e-3 * fs)))
    n = body.size
    head_open = (body[0] / float(i_open)) > 0.9
    tail_open = (body[-1] / float(i_open)) > 0.9
    spans: list[tuple[int, int]] = []
    for a, z in zip(edges[:-1], edges[1:]):
        a, z = int(a), int(z)
        if z - a < min_n:
            continue
        # Edge-aware rejection: only drop a fragment that touches an edge AND
        # whose touching end is already open pore (the old slow-exit artifact).
        if gap > 0 and ((a < gap and head_open) or (z > n - gap and tail_open)):
            continue
        spans.append((a, z))
    return spans


def extract_fragment_spans(body: np.ndarray, i_open: float, fs: float,
                           sigma_pA: float,
                           params: FragmentParams | None = None
                           ) -> list[tuple[int, int]]:
    return _fragment_spans(body, i_open, fs, sigma_pA, params or FragmentParams())


def extract_fragments(body: np.ndarray, i_open: float, fs: float,
                      sigma_pA: float, *,
                      params: FragmentParams | None = None,
                      event_index: int = -1) -> list[Fragment]:
    """Event body -> fragments with locally-aligned R1/R2 curves."""
    p = params or FragmentParams()
    out: list[Fragment] = []
    for a, z in _fragment_spans(body, i_open, fs, sigma_pA, p):
        curve = represent(body[a:z], i_open, fs, mode=p.mode, alpha=p.alpha, t0=0.0)
        out.append(Fragment(start=int(a), end=int(z), curve=curve,
                            event_index=int(event_index)))
    return out


def cluster_fragments(frags: list[np.ndarray], *, dist: str = "dtw",
                      cap: int = 1200, rng: np.random.Generator | None = None,
                      dist_thresh_frac: float = 0.5,
                      n_iter_dba: int = 5
                      ) -> tuple[np.ndarray, list[np.ndarray], float]:
    """Agglomerative clustering on a precomputed distance matrix.

    At most ``cap`` fragments are used to *build* the clusters; callers assign
    every fragment to the nearest center afterwards. A very small input gets a
    direct trivial answer instead of an ill-conditioned threshold.
    """
    require_research()
    from sklearn.cluster import AgglomerativeClustering

    n = len(frags)
    if n == 0:
        return np.array([], dtype=int), [], 0.0
    rng = rng or np.random.default_rng(0)
    if n > cap:
        idx = rng.choice(n, size=int(cap), replace=False)
        sample = [frags[i] for i in idx]
    else:
        sample = list(frags)

    if len(sample) == 1:
        return np.array([0], dtype=int), [np.asarray(sample[0], dtype=float)], 0.0

    M = distance_matrix(sample, dist)
    upper = M[np.triu_indices(len(sample), 1)]
    thr = float(dist_thresh_frac) * float(np.median(upper)) if upper.size else 0.0
    if not np.isfinite(thr) or thr <= 0:
        labels = np.arange(len(sample), dtype=int)
    else:
        model = AgglomerativeClustering(
            n_clusters=None, metric="precomputed", linkage="average",
            distance_threshold=thr)
        labels = np.asarray(model.fit_predict(M), dtype=int)

    centers: list[np.ndarray] = []
    for c in range(int(labels.max()) + 1):
        members = [sample[i] for i in np.flatnonzero(labels == c)]
        centers.append(dba(members, n_iter=n_iter_dba, name=dist)
                       if len(members) > 1 else np.asarray(members[0], dtype=float))
    return labels, centers, thr
