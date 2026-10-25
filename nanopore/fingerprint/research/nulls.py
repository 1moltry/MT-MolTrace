"""Null models, AUC and leave-one-file reproduction for shape discovery.

These are the honesty checks required by the archived project's rules:

* real data and every null go through the **same** extraction / representation /
  distance pipeline;
* the hard C1 gate is AUC ≥ 0.85 against same-pipeline nulls;
* C2 checks that a vocabulary reproduces on a held-out file, with center drift
  ≤ 50% of the within-class mean distance.

Nothing here changes a production result. The functions return plain dicts so
a CLI or the research workspace can display the numbers next to the warning
that the legacy vocabulary did not pass.
"""
from __future__ import annotations

import numpy as np
from scipy.signal import bessel, sosfiltfilt

from .corpus import EventCorpus
from .curves import REAL_BANDWIDTH_HZ, dist, distance_matrix
from .fragments import extract_fragments
from .model import GATE_NOTE, ShapeModel, _fragment_params


def lowpass(x: np.ndarray, fs: float, fc: float = REAL_BANDWIDTH_HZ,
            order: int = 4) -> np.ndarray:
    sos = bessel(order, min(float(fc), 0.49 * fs) / (fs / 2.0),
                 btype="low", output="sos")
    return sosfiltfilt(sos, np.asarray(x, dtype=float))


def _noise(n: int, sigma: float, fs: float, fc: float,
           rng: np.random.Generator) -> np.ndarray:
    y = lowpass(rng.normal(0.0, 1.0, n), fs, fc)
    sd = float(np.std(y))
    y = y - float(np.mean(y))
    return y / sd * float(sigma) if sd > 0 else np.zeros(n)


def synth_flat(length: int, level_pA: float, sigma: float, *,
               fs: float = 25_000.0, fc: float = REAL_BANDWIDTH_HZ,
               rng: np.random.Generator) -> np.ndarray:
    """N1-flat: constant level + same σ + same filter (no shape)."""
    return np.full(int(length), float(level_pA)) + _noise(int(length), sigma, fs, fc, rng)


def synth_telegraph(length: int, levels_pA: list[float], dwell_ms: float, *,
                    sigma: float = 2.0, fs: float = 25_000.0,
                    fc: float = REAL_BANDWIDTH_HZ,
                    rng: np.random.Generator) -> np.ndarray:
    """N1-telegraph: random-dwell two-state body with the same noise/filter."""
    length = int(length)
    if length <= 0:
        return np.zeros(0)
    lens: list[int] = []
    total = 0
    while total < length:
        n = max(4, int(round(rng.exponential(max(dwell_ms, 1e-3) / 1000.0 * fs))))
        lens.append(n)
        total += n
    x = np.concatenate([np.full(n, levels_pA[i % len(levels_pA)])
                        for i, n in enumerate(lens)])[:length]
    return x + _noise(length, sigma, fs, fc, rng)


def synth_random(length: int, i_open: float, *, sigma: float = 2.0,
                 fs: float = 25_000.0, fc: float = REAL_BANDWIDTH_HZ,
                 n_steps: int = 4, rng: np.random.Generator) -> np.ndarray:
    """N1-random: a few random levels and dwells, same noise/filter."""
    length = int(length)
    if length <= 0:
        return np.zeros(0)
    k = max(1, int(n_steps))
    levels = float(i_open) - rng.uniform(5.0, 80.0, k)
    weights = rng.uniform(0.5, 2.0, k)
    lens = np.maximum(2, np.round(weights / weights.sum() * length).astype(int))
    x = np.repeat(levels, lens)[:length]
    if x.size < length:
        x = np.pad(x, (0, length - x.size), mode="edge")
    return x + _noise(length, sigma, fs, fc, rng)


def phase_randomize(body: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """N2: keep the amplitude spectrum (hence PSD), randomize phase."""
    x = np.asarray(body, dtype=float)
    mean = float(x.mean())
    xc = x - mean
    X = np.fft.rfft(xc)
    ph = rng.uniform(0.0, 2.0 * np.pi, X.shape)
    ph[0] = 0.0
    if xc.size % 2 == 0:
        ph[-1] = 0.0
    y = np.fft.irfft(np.abs(X) * np.exp(1j * ph), n=xc.size)
    return y + mean


def shuffle_samples(body: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """N3: within-event sample shuffle (weakest control)."""
    y = np.asarray(body, dtype=float).copy()
    rng.shuffle(y)
    return y


def match_depth_dwell(corpus: EventCorpus, n_pair: int, *,
                      depth_tol_pA: float = 5.0, dwell_tol_log: float = 0.15,
                      rng: np.random.Generator) -> list[tuple[int, int]]:
    """N4: index pairs matched on depth and log-dwell (C3/C4 control)."""
    rows = corpus.body_meta()
    idx = rng.permutation(len(rows))
    out: list[tuple[int, int]] = []
    used: set[int] = set()
    for a in idx:
        if len(out) >= int(n_pair):
            break
        if a in used:
            continue
        best, bd = None, np.inf
        for b in idx:
            if b == a or b in used:
                continue
            dd = abs(rows[a]["depth_pA"] - rows[b]["depth_pA"])
            dl = abs(np.log10(max(rows[a]["dwell_s"], 1e-12))
                     - np.log10(max(rows[b]["dwell_s"], 1e-12)))
            if dd <= depth_tol_pA and dl <= dwell_tol_log:
                score = dd / max(depth_tol_pA, 1e-9) + dl / max(dwell_tol_log, 1e-9)
                if score < bd:
                    bd, best = score, b
        if best is not None:
            out.append((int(a), int(best)))
            used.add(int(a))
            used.add(int(best))
    return out


def auc(pos: np.ndarray, neg: np.ndarray) -> float:
    """AUC with smaller distances as the positive score."""
    pos = np.asarray(pos, dtype=float)
    neg = np.asarray(neg, dtype=float)
    pos = pos[np.isfinite(pos)]
    neg = neg[np.isfinite(neg)]
    if pos.size == 0 or neg.size == 0:
        return float("nan")
    allv = np.concatenate((pos, neg))
    ranks = np.argsort(np.argsort(allv)) + 1
    u = ranks[:pos.size].sum() - pos.size * (pos.size + 1) / 2.0
    return float(1.0 - u / (pos.size * neg.size))


def _fragment_metrics(body: np.ndarray, i_open: float, fs: float,
                      sigma: float, model: ShapeModel) -> tuple[float, list, list]:
    """Median min-center distance and fragments for one body."""
    fp = _fragment_params(model.params)
    frags = extract_fragments(body, i_open, fs, sigma, params=fp)
    if not frags or not model.centers:
        return float("nan"), frags, []
    dname = str(model.params.get("dist", "dtw"))
    per = [min(dist(dname, f.curve, c) for c in model.centers) for f in frags]
    return float(np.median(per)), frags, per


def event_metrics(corpus: EventCorpus, model: ShapeModel) -> np.ndarray:
    out = []
    for v in corpus.views:
        m, _, _ = _fragment_metrics(v.body, v.i_open, v.fs, v.sigma_open, model)
        out.append(m)
    return np.asarray(out, dtype=float)


def recurrence_score(frags: list, event_indices: list[int], dist_name: str,
                     cap: int = 400,
                     rng: np.random.Generator | None = None) -> float:
    """Median nearest distance to a fragment from a *different* event."""
    n = len(frags)
    if n == 0:
        return float("nan")
    rng = rng or np.random.default_rng(0)
    if n > cap:
        sel = rng.choice(n, size=int(cap), replace=False)
        frags = [frags[i] for i in sel]
        event_indices = [event_indices[i] for i in sel]
    out = []
    for i in range(len(frags)):
        best = np.inf
        for j in range(len(frags)):
            if event_indices[i] == event_indices[j]:
                continue
            d = dist(dist_name, frags[i].curve, frags[j].curve)
            if d < best:
                best = d
        if np.isfinite(best):
            out.append(best)
    return float(np.median(out)) if out else float("nan")


def null_report(corpus: EventCorpus, model: ShapeModel, *,
                max_events: int | None = None, seed: int = 0) -> dict:
    """N1-flat / N1-telegraph / N2-phase AUC and recurrence diagnostics."""
    rng = np.random.default_rng(seed)
    views = corpus.views[: int(max_events)] if max_events else corpus.views
    real, flat, tele, phase = [], [], [], []
    real_frags, flat_frags, tele_frags, phase_frags = [], [], [], []
    real_idx, flat_idx, tele_idx, phase_idx = [], [], [], []

    for i, v in enumerate(views):
        sigma = float(v.sigma_open) if np.isfinite(v.sigma_open) and v.sigma_open > 0 else 1.0
        level = float(np.median(v.body))
        bodies = {
            "real": v.body,
            "flat": synth_flat(v.n_samples, level, sigma, fs=v.fs, rng=rng),
            "tele": synth_telegraph(v.n_samples, [level, level - 0.08 * abs(v.i_open)],
                                    3.0, sigma=sigma, fs=v.fs, rng=rng),
            "phase": phase_randomize(v.body, rng),
        }
        for name, body in bodies.items():
            m, fr, _ = _fragment_metrics(body, v.i_open, v.fs, sigma, model)
            if name == "real":
                real.append(m)
                real_frags.extend(fr)
                real_idx.extend([i] * len(fr))
            elif name == "flat":
                flat.append(m)
                flat_frags.extend(fr)
                flat_idx.extend([i] * len(fr))
            elif name == "tele":
                tele.append(m)
                tele_frags.extend(fr)
                tele_idx.extend([i] * len(fr))
            else:
                phase.append(m)
                phase_frags.extend(fr)
                phase_idx.extend([i] * len(fr))

    dname = str(model.params.get("dist", "dtw"))
    return {
        "model_id": model.model_id,
        "n_events": len(views),
        "gate_note": GATE_NOTE,
        "auc_real_vs_N1flat": auc(np.asarray(real), np.asarray(flat)),
        "auc_real_vs_N1tele": auc(np.asarray(real), np.asarray(tele)),
        "auc_real_vs_N2phase": auc(np.asarray(real), np.asarray(phase)),
        "median_distance": {
            "real": float(np.nanmedian(real)) if real else float("nan"),
            "N1flat": float(np.nanmedian(flat)) if flat else float("nan"),
            "N1tele": float(np.nanmedian(tele)) if tele else float("nan"),
            "N2phase": float(np.nanmedian(phase)) if phase else float("nan"),
        },
        "recurrence": {
            "real": recurrence_score(real_frags, real_idx, dname, rng=rng),
            "N1flat": recurrence_score(flat_frags, flat_idx, dname, rng=rng),
            "N1tele": recurrence_score(tele_frags, tele_idx, dname, rng=rng),
            "N2phase": recurrence_score(phase_frags, phase_idx, dname, rng=rng),
        },
    }


def _center_drift(model_a: ShapeModel, model_b: ShapeModel) -> float:
    """Median nearest-center distance between two vocabularies, normalized."""
    if not model_a.centers or not model_b.centers:
        return float("nan")
    dname = str(model_a.params.get("dist", "dtw"))
    nearest = [min(dist(dname, a, b) for b in model_b.centers)
               for a in model_a.centers]
    M = distance_matrix(model_a.centers, dname)
    if M.size <= 1:
        within = float("nan")
    else:
        upper = M[np.triu_indices(len(model_a.centers), 1)]
        within = float(np.median(upper)) if upper.size else float("nan")
    drift = float(np.median(nearest))
    return drift / within if np.isfinite(within) and within > 0 else float("nan")


def leave_one_file(corpus: EventCorpus, method, params: dict | None = None,
                   *, seed: int = 0, with_nulls: bool = False) -> dict:
    """Fit on all but one source, decode the held-out source, repeat."""
    sources = corpus.source_names()
    if len(sources) < 2:
        return {"status": "insufficient_sources", "n_sources": len(sources),
                "gate_note": GATE_NOTE}
    if method is None:
        raise ValueError("leave_one_file needs a CorpusShapeMethod")
    reference = method.fit(corpus, params)
    folds = []
    for held in sources:
        train = EventCorpus(
            [v for v, s in zip(corpus.views, corpus.sources) if s != held],
            [s for s in corpus.sources if s != held],
            dict(corpus.meta))
        test = EventCorpus(
            [v for v, s in zip(corpus.views, corpus.sources) if s == held],
            [s for s in corpus.sources if s == held],
            dict(corpus.meta))
        if not train.views or not test.views:
            continue
        try:
            model = method.fit(train, params)
        except Exception as exc:  # noqa: BLE001 — one fold is not fatal
            folds.append({"held_out": held, "error": f"{type(exc).__name__}: {exc}"})
            continue
        metrics = event_metrics(test, model)
        fold = {
            "held_out": held,
            "n_train": train.n_events,
            "n_test": test.n_events,
            "n_centers": len(model.centers),
            "median_center_distance": float(np.nanmedian(metrics))
            if metrics.size else float("nan"),
            "center_drift_frac": _center_drift(model, reference),
        }
        if with_nulls:
            fold["nulls"] = null_report(test, model, seed=seed)
        folds.append(fold)
    # Folds set the process-wide active model as a side effect; restore the
    # full-corpus reference so a later decode does not silently use a fold.
    from .model import set_active_model
    set_active_model(reference)
    return {"status": "ok", "n_sources": len(sources), "folds": folds,
            "gate_note": GATE_NOTE}
