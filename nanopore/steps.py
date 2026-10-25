"""Event-internal step detection: DP + BIC piecewise-constant fit.

Ported from the sugar-sequencing project ``npsweep/steps.py`` (2026-10-22),
keeping the calibrated algorithm and dropping the .mat/CSV I/O and CLI.

Method (unchanged from the source):
    optimal-partition DP with an L2 cost, BIC to choose the number of
    segments, then merge segments that are too short or too shallow.

Edge trimming has two different criteria: ``t_in`` skips the entry
transition (derivative settles), ``t_out`` ends when the signal is back at
the open-pore level (so slow exits are not cut short).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass

import numpy as np

try:                                   # optional accelerator, exact same result
    from numba import njit
except Exception:                      # noqa: BLE001 — absent/broken numba is fine
    njit = None

# DP length cap: longer events are block-averaged down to this many points.
N_DP_MAX = 5000

# Calibrated working point (source: sugar project, 2026-10-01).
TAU_MIN_US = 250.0
AMP_MIN_PA = 10.0
K_MAX = 30

# Edge trimming (source: 2026-10-06, per-event adaptive).
EDGE_WIN = 5
EDGE_K = 4.0
EDGE_SETTLE_MS = 0.24
EDGE_LEVEL_M = 3.0


@dataclass
class Step:
    """One piecewise-constant sub-step."""

    level_pA: float            # mean current of the segment (pA)
    level_r: float             # level_pA / i_open
    tau_s: float               # dwell time (s)
    amp_pA: float              # jump relative to the previous segment (pA)
    snr: float                 # (|amp|/sigma) * sqrt(tau * fs)


def _dp_fit_python(c: np.ndarray, c2: np.ndarray, n: int,
                   k_max: int) -> tuple[np.ndarray, list[np.ndarray | None]]:
    """Reference DP (numpy). Same recurrence as the compiled kernel below."""
    prev = np.full(n + 1, np.inf)
    prev[0] = 0.0
    backs: list[np.ndarray | None] = [None] * (k_max + 1)
    rss = np.full(k_max, np.inf)
    for k in range(1, k_max + 1):
        cur = np.full(n + 1, np.inf)
        back = np.zeros(n + 1, dtype=np.int64)
        for j in range(k, n + 1):
            i = np.arange(k - 1, j)
            di = (j - i).astype(np.float64)
            seg = (c2[j] - c2[i]) - (c[j] - c[i]) ** 2 / di
            vals = prev[i] + seg
            m = int(np.argmin(vals))
            cur[j] = vals[m]
            back[j] = i[m]
        backs[k] = back
        prev = cur
        rss[k - 1] = cur[n]
    return rss, backs


if njit is not None:
    @njit(cache=not getattr(sys, "frozen", False))
    def _dp_fit_kernel(c: np.ndarray, c2: np.ndarray, n: int, k_max: int):
        prev = np.full(n + 1, np.inf)
        prev[0] = 0.0
        backs = np.zeros((k_max + 1, n + 1), dtype=np.int64)
        rss = np.full(k_max, np.inf)
        for k in range(1, k_max + 1):
            cur = np.full(n + 1, np.inf)
            back = np.zeros(n + 1, dtype=np.int64)
            for j in range(k, n + 1):
                best = np.inf
                bi = -1
                for i in range(k - 1, j):
                    di = float(j - i)
                    seg = (c2[j] - c2[i]) - (c[j] - c[i]) ** 2 / di
                    v = prev[i] + seg
                    if v < best:
                        best = v
                        bi = i
                cur[j] = best
                back[j] = bi
            backs[k] = back
            prev = cur
            rss[k - 1] = cur[n]
        return rss, backs


def _dp_fit(y: np.ndarray, k_max: int):
    """Optimal partition DP; compiled when numba is available.

    The kernel is a pure loop with the same floating-point operations as the
    numpy reference, so both paths return identical RSS and back-pointers.
    """
    n = y.size
    c = np.concatenate(([0.0], np.cumsum(y)))
    c2 = np.concatenate(([0.0], np.cumsum(y * y)))
    if njit is not None:
        return _dp_fit_kernel(c, c2, n, k_max)
    return _dp_fit_python(c, c2, n, k_max)


def _segment_bounds(rss: np.ndarray, backs: list[np.ndarray | None],
                    n: int, k: int) -> list[int]:
    """Rebuild the k-segment boundaries (including 0 and n)."""
    bounds = [n]
    j = n
    for kk in range(k, 0, -1):
        j = int(backs[kk][j])
        bounds.append(j)
    return sorted(set(bounds))


def _bic_k(rss: np.ndarray, n: int) -> int:
    """BIC segment count: argmin n*ln(RSS_k/n) + (2k-1)*ln(n)."""
    ks = np.arange(1, rss.size + 1)
    rss_safe = np.where(rss > 0, rss, np.finfo(float).tiny)
    bic = n * np.log(rss_safe / n) + (2 * ks - 1) * np.log(n)
    return int(np.argmin(bic)) + 1


def _merge_weak(means: list[float], lengths: list[int], fs: float, decim: int,
                tau_min_s: float, amp_min: float) -> tuple[list[float], list[int]]:
    """Merge segments that are too short or too shallow, until stable."""
    means = list(means)
    lengths = list(lengths)
    changed = True
    while changed and len(means) > 1:
        changed = False
        for m in range(len(means)):                       # short segments first
            if lengths[m] * decim / fs < tau_min_s:
                if m == 0:
                    tgt = 1
                elif m == len(means) - 1:
                    tgt = m - 1
                else:
                    tgt = m - 1 if lengths[m - 1] >= lengths[m + 1] else m + 1
                lo, hi = min(m, tgt), max(m, tgt)
                wl = lengths[lo] + lengths[hi]
                wm = (means[lo] * lengths[lo] + means[hi] * lengths[hi]) / wl
                means = means[:lo] + [wm] + means[hi + 1:]
                lengths = lengths[:lo] + [wl] + lengths[hi + 1:]
                changed = True
                break
        if changed:
            continue
        for m in range(1, len(means)):                    # shallow segments
            if abs(means[m] - means[m - 1]) < amp_min:
                wl = lengths[m] + lengths[m - 1]
                wm = (means[m] * lengths[m] + means[m - 1] * lengths[m - 1]) / wl
                means = means[:m - 1] + [wm] + means[m + 1:]
                lengths = lengths[:m - 1] + [wl] + lengths[m + 1:]
                changed = True
                break
    return means, lengths


def _merge_low_snr(means: list[float], lengths: list[int], fs: float, decim: int,
                   sigma_pA: float, snr_min: float) -> tuple[list[float], list[int]]:
    """Optionally merge segments whose step is not significant.

    The source implementation carried ``snr_min`` but never applied it; here
    it is opt-in (``snr_min = 0`` disables it), so the default output stays
    identical to the calibrated source.
    """
    if snr_min <= 0 or sigma_pA <= 0 or len(means) < 2:
        return means, lengths
    means = list(means)
    lengths = list(lengths)
    changed = True
    while changed and len(means) > 1:
        changed = False
        for m in range(1, len(means)):
            tau_s = lengths[m] * decim / fs
            amp = abs(means[m] - means[m - 1])
            snr = (amp / sigma_pA) * np.sqrt(tau_s * fs)
            if snr < snr_min:
                wl = lengths[m] + lengths[m - 1]
                wm = (means[m] * lengths[m] + means[m - 1] * lengths[m - 1]) / wl
                means = means[:m - 1] + [wm] + means[m + 1:]
                lengths = lengths[:m - 1] + [wl] + lengths[m + 1:]
                changed = True
                break
    return means, lengths


def _first_long_run(mask: np.ndarray, m: int) -> int:
    """Start index of the earliest True run of length >= m, else len(mask)."""
    if m <= 0:
        return 0
    run = 0
    for i, v in enumerate(mask):
        run = run + 1 if v else 0
        if run >= m:
            return i - m + 1
    return int(mask.size)


def edge_bounds(body: np.ndarray, sigma_pA: float, fs: float,
                i_open: float | None = None, *,
                win: int = EDGE_WIN, k: float = EDGE_K,
                settle_ms: float = EDGE_SETTLE_MS,
                level_m: float = EDGE_LEVEL_M) -> tuple[int, int]:
    """Find the fingerprint start/end samples inside ``body``.

    ``t_in`` uses the derivative (skip the entry ramp). ``t_out`` uses the
    level criterion when ``i_open`` is given (signal back at the open pore),
    otherwise it falls back to the derivative. Returns half-open indices.
    """
    n = body.size
    m = int(round(settle_ms * 1e-3 * fs))
    if n < 3 * m + win + 2 or sigma_pA <= 0:
        return 0, n
    kernel = np.ones(win) / win
    xs = np.convolve(np.asarray(body, dtype=np.float64), kernel, mode="same")
    dx = np.abs(np.diff(xs))

    thr = k * sigma_pA / np.sqrt(win)
    settled = dx < thr
    t_in = _first_long_run(settled[:max(0, n - win)], m) + win

    if i_open is not None:
        lvl_thr = i_open - level_m * sigma_pA
        idx = np.flatnonzero(xs > lvl_thr)
        t_out = int(idx[-1]) + 1 if idx.size else n
    else:
        rev = _first_long_run(settled[::-1], m)
        t_out = n - (rev + win) if rev < settled.size else n

    t_in = int(np.clip(t_in, 0, n))
    t_out = int(np.clip(t_out, 0, n))
    if t_out - t_in < max(2, m):
        return 0, n
    return t_in, t_out


def detect_steps(body: np.ndarray, fs: float, i_open: float, *,
                 sigma_pA: float = 1.0, k_max: int = K_MAX,
                 tau_min_us: float = TAU_MIN_US, amp_min: float = AMP_MIN_PA,
                 snr_min: float = 0.0, n_dp_max: int = N_DP_MAX
                 ) -> tuple[list[Step], int, int]:
    """Fit piecewise-constant segments to an already-trimmed event body.

    Returns ``(steps, k_bic, decimation_factor)``.
    """
    body = np.asarray(body, dtype=np.float64).ravel()
    n = body.size
    if n <= 2:
        return [], 1, 1

    decim = max(1, int(np.ceil(n / n_dp_max)))
    if decim > 1:
        n_use = (n // decim) * decim
        y = body[:n_use].reshape(-1, decim).mean(axis=1)
    else:
        y = body
    ny = y.size

    rss, backs = _dp_fit(y, min(k_max, ny))
    k = _bic_k(rss, ny)
    bounds = _segment_bounds(rss, backs, ny, k)

    c = np.concatenate(([0.0], np.cumsum(y)))
    means = [float((c[b1] - c[b0]) / (b1 - b0))
             for b0, b1 in zip(bounds[:-1], bounds[1:])]
    lengths = [int(b1 - b0) for b0, b1 in zip(bounds[:-1], bounds[1:])]
    means, lengths = _merge_weak(means, lengths, fs, decim,
                                 tau_min_us * 1e-6, amp_min)
    means, lengths = _merge_low_snr(means, lengths, fs, decim, sigma_pA, snr_min)
    k = len(means)

    steps: list[Step] = []
    for m, (mu, ln) in enumerate(zip(means, lengths)):
        tau_s = ln * decim / fs
        amp = abs(mu - means[m - 1]) if m > 0 else 0.0
        snr = (amp / sigma_pA) * np.sqrt(tau_s * fs) if sigma_pA > 0 else np.inf
        steps.append(Step(level_pA=mu, level_r=mu / i_open, tau_s=tau_s,
                          amp_pA=amp, snr=float(snr)))
    return steps, k, decim
