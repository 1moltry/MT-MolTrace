"""Event-internal step detection: DP + BIC piecewise-constant fit.

Ported from the sugar-sequencing project ``npsweep/steps.py`` (2026-10-22),
keeping the calibrated algorithm and dropping the .mat/CSV I/O and CLI.

Method (unchanged from the source):
    optimal-partition DP with an L2 cost, BIC to choose the number of
    segments, then merge segments that are too short or too shallow.

Edge trimming has two different criteria: ``t_in`` skips the entry
transition (derivative settles), ``t_out`` ends when the signal is back at
the open-pore level (so slow exits are not cut short). Both criteria are
direction-aware: downward events return to the open pore from below, upward
events from above, and bidirectional events must come back inside a band.

Segment boundaries are integer samples end to end. The decimation remainder
is folded into the last segment, so the final segment always reaches ``t_out``
and the widths sum to the trimmed body length exactly.
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
#: Smoothing window in milliseconds. A time window keeps 25 kHz and 50 kHz
#: recordings on the same physical scale; ``EDGE_WIN`` is the legacy
#: sample-count override kept for old configs.
EDGE_WIN_MS = 0.2
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
    # Integer sample offsets inside the trimmed body (half-open). Added in
    # phase 4; tail-defaulted so old positional construction keeps working.
    start: int = 0
    end: int = 0

    @property
    def length(self) -> int:
        return max(0, int(self.end) - int(self.start))


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


def effective_sample_size(y: np.ndarray, max_lag: int | None = None) -> float:
    """Autocorrelation-based effective sample size of a (noise) series.

    A low-passed trace is strongly autocorrelated, so the decimated DP points
    are *not* independent. Treating them as independent makes the BIC
    complexity penalty too small and over-segments long events. This estimator
    uses the initial positive autocorrelation sum,

        n_eff = n / (1 + 2 * sum_{k=1..L} rho_k)

    and stops at the first non-positive rho (or ``max_lag``). Returns ``n``
    when the series is white.
    """
    x = np.asarray(y, dtype=np.float64).ravel()
    n = x.size
    if n < 8:
        return float(max(n, 1))
    x = x - float(np.mean(x))
    denom = float(np.dot(x, x))
    if not np.isfinite(denom) or denom <= 0:
        return float(n)
    lag_max = min(n // 4, max_lag if max_lag is not None else 200)
    rho_sum = 0.0
    for lag in range(1, lag_max + 1):
        rho = float(np.dot(x[:-lag], x[lag:]) / denom)
        if rho <= 0:
            break
        rho_sum += rho
    return float(max(1.0, n / (1.0 + 2.0 * rho_sum)))


def _bic_k(rss: np.ndarray, n: int, *, n_eff: float | None = None,
           penalty: float = 1.0) -> int:
    """BIC segment count with an optional effective-sample-size correction.

    ``BIC = n_eff * ln(RSS_k/n) + penalty * (2k-1) * ln(n_eff)``. With
    ``n_eff=n`` and ``penalty=1`` this is exactly the calibrated source
    behaviour. Autocorrelated noise makes ``n_eff`` much smaller than the
    decimated point count; both the likelihood gain and the complexity term
    are then weighted by the evidence actually present, which suppresses the
    over-segmentation that treats neighbouring samples as independent.
    """
    ks = np.arange(1, rss.size + 1)
    rss_safe = np.where(rss > 0, rss, np.finfo(float).tiny)
    nel = float(n if n_eff is None else max(2.0, n_eff))
    bic = nel * np.log(rss_safe / n) + penalty * (2 * ks - 1) * np.log(nel)
    return int(np.argmin(bic)) + 1


def bic_curve(rss: np.ndarray, n: int, *, n_eff: float | None = None,
              penalty: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(ks, bic)`` for every candidate segment count (diagnostics)."""
    ks = np.arange(1, rss.size + 1)
    rss_safe = np.where(rss > 0, rss, np.finfo(float).tiny)
    nel = float(n if n_eff is None else max(2.0, n_eff))
    bic = nel * np.log(rss_safe / n) + penalty * (2 * ks - 1) * np.log(nel)
    return ks, bic


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


def edge_window_samples(fs: float, *, win_ms: float | None = EDGE_WIN_MS,
                        win: int | None = None) -> int:
    """Samples in the edge-smoothing window.

    ``win_ms`` (a physical time) takes precedence, so 25 kHz and 50 kHz
    recordings use the same physical window. ``win`` is the legacy
    sample-count override and is only used when ``win_ms`` is ``None`` or 0.
    """
    if win_ms is not None and win_ms > 0:
        return max(1, int(round(float(win_ms) * 1e-3 * fs)))
    return max(1, int(win if win is not None else EDGE_WIN))


def edge_bounds(body: np.ndarray, sigma_pA: float, fs: float,
                i_open: float | None = None, *,
                win_ms: float | None = EDGE_WIN_MS, win: int | None = None,
                k: float = EDGE_K, settle_ms: float = EDGE_SETTLE_MS,
                level_m: float = EDGE_LEVEL_M,
                direction: int = 0) -> tuple[int, int]:
    """Find the fingerprint start/end samples inside ``body``.

    ``t_in`` uses the derivative (skip the entry ramp). ``t_out`` uses a
    direction-aware level criterion when ``i_open`` is given: a downward
    event must rise back above the open pore, an upward event must fall back
    below it, and a bidirectional event must return inside a band around it.
    Without ``i_open`` it falls back to the derivative. Returns half-open
    indices.
    """
    n = body.size
    win_s = edge_window_samples(fs, win_ms=win_ms, win=win)
    m = int(round(settle_ms * 1e-3 * fs))
    if n < 3 * m + win_s + 2 or sigma_pA <= 0:
        return 0, n
    kernel = np.ones(win_s) / win_s
    # Edge-pad before smoothing. A plain ``mode="same"`` convolution pads with
    # zeros, which drags the last samples toward 0 pA and makes a downward
    # event look as if it never returned to the open pore (t_out = n).
    pad = win_s // 2
    padded = np.pad(np.asarray(body, dtype=np.float64),
                    (pad, win_s - 1 - pad), mode="edge")
    xs = np.convolve(padded, kernel, mode="valid")
    dx = np.abs(np.diff(xs))

    thr = k * sigma_pA / np.sqrt(win_s)
    settled = dx < thr
    t_in = _first_long_run(settled[:max(0, n - win_s)], m) + win_s

    if i_open is not None and np.isfinite(i_open):
        band = level_m * sigma_pA
        if direction > 0:                     # upward event: return from above
            inside = xs < i_open + band
        elif direction < 0:                   # downward event: return from below
            inside = xs > i_open - band
        else:                                 # bidirectional: return to the band
            inside = np.abs(xs - i_open) <= band
        idx = np.flatnonzero(~inside)
        t_out = int(idx[-1]) + 1 if idx.size else n
    else:
        rev = _first_long_run(settled[::-1], m)
        t_out = n - (rev + win_s) if rev < settled.size else n

    t_in = int(np.clip(t_in, 0, n))
    t_out = int(np.clip(t_out, 0, n))
    if t_out - t_in < max(2, m):
        return 0, n
    return t_in, t_out


def detect_steps(body: np.ndarray, fs: float, i_open: float, *,
                 sigma_pA: float = 1.0, k_max: int = K_MAX,
                 tau_min_us: float = TAU_MIN_US, amp_min: float = AMP_MIN_PA,
                 snr_min: float = 0.0, n_dp_max: int = N_DP_MAX,
                 bic_penalty: float = 1.0, bic_n_eff: float = 0.0
                 ) -> tuple[list[Step], int, int]:
    """Fit piecewise-constant segments to an already-trimmed event body.

    ``bic_n_eff``: ``0`` keeps the source behaviour (decimated points counted
    as independent); a positive value uses that effective sample size; a
    negative value estimates it from the autocorrelation of ``y``.
    ``bic_penalty`` scales the BIC complexity term (>1 suppresses
    over-segmentation). Both are diagnostics-first: the defaults reproduce the
    calibrated source output exactly.

    Returns ``(steps, k_bic, decimation_factor)``. Step start/end are integer
    sample offsets in ``body`` and the last step always ends at ``len(body)``.
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
    n_eff = None
    if bic_n_eff < 0:
        n_eff = effective_sample_size(y)
    elif bic_n_eff > 0:
        n_eff = float(bic_n_eff)
    k = _bic_k(rss, ny, n_eff=n_eff, penalty=bic_penalty)
    bounds = _segment_bounds(rss, backs, ny, k)

    c = np.concatenate(([0.0], np.cumsum(y)))
    means = [float((c[b1] - c[b0]) / (b1 - b0))
             for b0, b1 in zip(bounds[:-1], bounds[1:])]
    lengths = [int(b1 - b0) for b0, b1 in zip(bounds[:-1], bounds[1:])]
    means, lengths = _merge_weak(means, lengths, fs, decim,
                                 tau_min_us * 1e-6, amp_min)
    means, lengths = _merge_low_snr(means, lengths, fs, decim, sigma_pA, snr_min)
    k = len(means)

    # Integer sample lengths. The decimation remainder belongs to the last
    # segment; without this the final segment stops short of t_out and the
    # exported coverage silently loses samples.
    lengths = [int(ln) * decim for ln in lengths]
    if lengths:
        lengths[-1] += n - sum(lengths)

    steps: list[Step] = []
    cursor = 0
    for m, (mu, ln) in enumerate(zip(means, lengths)):
        end = cursor + int(ln)
        tau_s = (end - cursor) / fs
        amp = abs(mu - means[m - 1]) if m > 0 else 0.0
        snr = (amp / sigma_pA) * np.sqrt(tau_s * fs) if sigma_pA > 0 else np.inf
        steps.append(Step(level_pA=mu, level_r=mu / i_open, tau_s=tau_s,
                          amp_pA=amp, snr=float(snr),
                          start=cursor, end=end))
        cursor = end
    return steps, k, decim


def trim_exit_transition(steps: list[Step], *, i_open: float,
                         i_blockade: float, max_frac: float = 0.25,
                         min_tail: int = 2, max_tail_frac: float = 0.5,
                         max_seg_frac: float = 0.25) -> list[Step]:
    """Drop a trailing slow-exit ramp that the constant-level fit split up.

    A slow return to the open pore is a transition, not a fingerprint, but the
    level-based ``t_out`` deliberately follows it to the end so the event is
    not cut short. The piecewise-constant fit then models the ramp as a few
    short, monotonically rising (or falling) segments. Such a tail is removed
    when it is at least ``min_tail`` segments long, ends within
    ``max_frac * |i_open - i_blockade|`` of the open pore, and occupies no more
    than ``max_tail_frac`` of the body. A segment wider than ``max_seg_frac``
    of the body is treated as a stable plateau and ends the search, so the
    stable level itself is never removed.
    """
    n = len(steps)
    depth = abs(float(i_open) - float(i_blockade))
    total_width = sum(s.length for s in steps)
    if (n < min_tail + 1 or not np.isfinite(depth) or depth <= 0
            or max_frac <= 0 or total_width <= 0):
        return steps

    last_dist = abs(float(steps[-1].level_pA) - float(i_open))
    if last_dist > max_frac * depth:
        return steps

    tail_start = n - 1
    prev_dist = last_dist
    for i in range(n - 2, -1, -1):
        if steps[i].length > max_seg_frac * total_width:
            break                      # a stable plateau, not part of the ramp
        dist = abs(float(steps[i].level_pA) - float(i_open))
        if dist <= prev_dist:          # not moving toward the open pore
            break
        tail_start = i
        prev_dist = dist
    if tail_start == 0 or (n - tail_start) < min_tail:
        return steps

    tail_width = sum(s.length for s in steps[tail_start:])
    if tail_width > max_tail_frac * total_width:
        return steps
    return steps[:tail_start]
