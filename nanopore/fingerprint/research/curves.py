"""Representation, distances and shape centers for the research layer.

Ported from the archived deep-signal project (``work/shape_lib.py``). The
representation follows the project's documented choices:

* R1 = ``(t / 1 ms, alpha * (I / i_open - u_ref))`` — amplitude is part of the
  shape (the explicit ``alpha`` makes that assumption sweepable);
* R2 = R1 divided by its own range — the pure-shape control arm;
* DTW is normalized by the two lengths (Soni 2025); discrete Fréchet is a true
  metric and is kept as a second opinion; Euclidean-on-resampled is a baseline
  only (resampling imposes a length assumption).

All functions are Qt-free. Numba accelerates the distance kernels when it is
available; the pure NumPy path is the reference.
"""
from __future__ import annotations

import numpy as np

from .deps import require_research

TIME_FLOOR_MS = 0.47          # empirical resolution floor (legacy PSD estimate)
REAL_BANDWIDTH_HZ = 1200.0
DEFAULT_DRIFT_WIN_MS = 20.0


# --------------------------------------------------------------------------- #
# Representation
# --------------------------------------------------------------------------- #

def detrend_median(body: np.ndarray, fs: float, *, win_ms: float = DEFAULT_DRIFT_WIN_MS
                   ) -> np.ndarray:
    """Subtract a long median baseline; the window is capped to ``n/3``."""
    from scipy.ndimage import median_filter

    x = np.asarray(body, dtype=float).ravel()
    n = x.size
    if n < 5:
        return x - float(x.mean())
    win = max(5, min(int(round(win_ms * 1e-3 * fs)), n // 3))
    if win % 2 == 0:
        win += 1
    return x - median_filter(x, size=win, mode="nearest")


def represent(body: np.ndarray, i_open: float, fs: float, *,
              mode: str = "R1", alpha: float = 1.0, u_ref: float = 0.0,
              tau_ref_ms: float = 1.0, detrend: bool = False,
              drift_win_ms: float = DEFAULT_DRIFT_WIN_MS,
              t0: float = 0.0) -> np.ndarray:
    """Event body -> an ``(n, 2)`` ``(time, current)`` curve."""
    x = detrend_median(body, fs, win_ms=drift_win_ms) if detrend else body
    u = np.asarray(x, dtype=float) / float(i_open)
    y = float(alpha) * (u - float(u_ref))
    if mode == "R2":
        rng = float(np.ptp(y))
        if rng > 0:
            y = y / rng
    t = float(t0) + np.arange(np.asarray(body).size) / float(fs) * 1e3 / float(tau_ref_ms)
    return np.stack([t, y], axis=1)


def make_known_shape(kind: str, n: int = 60, amp: float = 1.0,
                     seed_noise: float = 0.0,
                     rng: np.random.Generator | None = None) -> np.ndarray:
    """Build a synthetic ``(n, 2)`` curve for distance/center tests."""
    t = np.linspace(0, 1, n)
    if kind == "flat":
        y = np.zeros(n)
    elif kind == "platform":
        y = np.zeros(n)
        y[n // 3: 2 * n // 3] = -amp
    elif kind == "spike":
        y = np.zeros(n)
        c, w = n // 2, max(2, n // 20)
        y[c - w:c + w] = -amp
    elif kind == "ramp":
        y = np.zeros(n)
        y[n // 3:] = -amp * np.linspace(0, 1, n - n // 3)
    elif kind == "step":
        y = np.zeros(n)
        y[n // 2:] = -amp
    elif kind == "valley":
        y = -amp * np.exp(-((t - 0.5) ** 2) / (2 * 0.12 ** 2))
    elif kind == "bump":
        y = -amp * np.sin(np.pi * t) ** 2
    else:
        raise ValueError(f"unknown shape {kind!r}")
    if seed_noise > 0 and rng is not None:
        y = y + rng.normal(0.0, seed_noise, n)
    return np.stack([t, y], axis=1)


# --------------------------------------------------------------------------- #
# Distance kernels
# --------------------------------------------------------------------------- #

def _point_dist(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    d = a[:, None, :] - b[None, :, :]
    return np.sqrt(np.sum(d * d, axis=2))


try:                                      # optional accelerator
    from numba import njit

    @njit(cache=True)
    def _dtw_cost_nb(a, b, band):          # noqa: ANN001
        na, nb = a.shape[0], b.shape[0]
        inf = 1e300
        prev = np.full(nb + 1, inf)
        prev[0] = 0.0
        cur = np.full(nb + 1, inf)
        for i in range(1, na + 1):
            cur[:] = inf
            if band >= 0:
                jlo = max(1, i - band)
                jhi = min(nb, i + band)
            else:
                jlo, jhi = 1, nb
            for j in range(jlo, jhi + 1):
                dx = a[i - 1, 0] - b[j - 1, 0]
                dy = a[i - 1, 1] - b[j - 1, 1]
                d = (dx * dx + dy * dy) ** 0.5
                m = prev[j - 1]
                if prev[j] < m:
                    m = prev[j]
                if cur[j - 1] < m:
                    m = cur[j - 1]
                cur[j] = d + m
            tmp = prev
            prev = cur
            cur = tmp
        return prev[nb]

    @njit(cache=True)
    def _dtw_path_nb(a, b):                 # noqa: ANN001
        na, nb = a.shape[0], b.shape[0]
        inf = 1e300
        dp = np.full((na + 1, nb + 1), inf)
        back = np.zeros((na + 1, nb + 1), np.int8)
        dp[0, 0] = 0.0
        for i in range(1, na + 1):
            for j in range(1, nb + 1):
                dx = a[i - 1, 0] - b[j - 1, 0]
                dy = a[i - 1, 1] - b[j - 1, 1]
                d = (dx * dx + dy * dy) ** 0.5
                m = dp[i - 1, j - 1]
                k = 0
                if dp[i - 1, j] < m:
                    m, k = dp[i - 1, j], 1
                if dp[i, j - 1] < m:
                    m, k = dp[i, j - 1], 2
                dp[i, j] = d + m
                back[i, j] = k
        path = np.empty((na + nb, 2), np.int64)
        c, i, j = 0, na, nb
        while i > 0 or j > 0:
            path[c, 0] = i - 1
            path[c, 1] = j - 1
            c += 1
            k = back[i, j]
            if k == 0:
                i -= 1
                j -= 1
            elif k == 1:
                i -= 1
            else:
                j -= 1
        return dp[na, nb], path[c - 1::-1]

    @njit(cache=True)
    def _frechet_nb(a, b):                  # noqa: ANN001
        na, nb = a.shape[0], b.shape[0]
        prev = np.empty(nb)
        d = ((a[0, 0] - b[0, 0]) ** 2 + (a[0, 1] - b[0, 1]) ** 2) ** 0.5
        prev[0] = d
        for j in range(1, nb):
            d = ((a[0, 0] - b[j, 0]) ** 2 + (a[0, 1] - b[j, 1]) ** 2) ** 0.5
            prev[j] = d if d > prev[j - 1] else prev[j - 1]
        cur = np.empty(nb)
        for i in range(1, na):
            d = ((a[i, 0] - b[0, 0]) ** 2 + (a[i, 1] - b[0, 1]) ** 2) ** 0.5
            cur[0] = d if d > prev[0] else prev[0]
            for j in range(1, nb):
                d = ((a[i, 0] - b[j, 0]) ** 2 + (a[i, 1] - b[j, 1]) ** 2) ** 0.5
                m = prev[j - 1]
                if prev[j] < m:
                    m = prev[j]
                if cur[j - 1] < m:
                    m = cur[j - 1]
                cur[j] = d if d > m else m
            tmp = prev
            prev = cur
            cur = tmp
        return prev[nb - 1]

    _HAVE_NUMBA = True
except Exception:                          # noqa: BLE001 — pure fallback is fine
    _HAVE_NUMBA = False


def _dtw_python(D: np.ndarray, band: int) -> float:
    na, nb = D.shape
    inf = 1e300
    prev = np.full(nb + 1, inf)
    prev[0] = 0.0
    for i in range(1, na + 1):
        cur = np.full(nb + 1, inf)
        if band >= 0:
            jlo = max(1, i - band)
            jhi = min(nb, i + band)
        else:
            jlo, jhi = 1, nb
        for j in range(jlo, jhi + 1):
            cur[j] = D[i - 1, j - 1] + min(prev[j - 1], prev[j], cur[j - 1])
        prev = cur
    return float(prev[nb])


def _dtw_path_python(a: np.ndarray, b: np.ndarray) -> tuple[float, np.ndarray]:
    D = _point_dist(a, b)
    na, nb = D.shape
    inf = 1e300
    dp = np.full((na + 1, nb + 1), inf)
    back = np.zeros((na + 1, nb + 1), np.int8)
    dp[0, 0] = 0.0
    for i in range(1, na + 1):
        for j in range(1, nb + 1):
            m = dp[i - 1, j - 1]
            k = 0
            if dp[i - 1, j] < m:
                m, k = dp[i - 1, j], 1
            if dp[i, j - 1] < m:
                m, k = dp[i, j - 1], 2
            dp[i, j] = D[i - 1, j - 1] + m
            back[i, j] = k
    path = []
    i, j = na, nb
    while i > 0 or j > 0:
        path.append((i - 1, j - 1))
        k = back[i, j]
        if k == 0:
            i -= 1
            j -= 1
        elif k == 1:
            i -= 1
        else:
            j -= 1
    return float(dp[na, nb]), np.asarray(path[::-1], dtype=np.int64)


def dtw(a: np.ndarray, b: np.ndarray, *, band_frac: float | None = 0.25,
        want_path: bool = False):
    """Length-normalized DTW distance (optionally with its warping path)."""
    a = np.ascontiguousarray(a, dtype=np.float64)
    b = np.ascontiguousarray(b, dtype=np.float64)
    band = -1
    if band_frac is not None:
        band = max(int(round(band_frac * max(a.shape[0], b.shape[0]))),
                   abs(a.shape[0] - b.shape[0]))
    if _HAVE_NUMBA:
        if want_path:
            cost, path = _dtw_path_nb(a, b)
        else:
            cost = _dtw_cost_nb(a, b, band)
    else:
        if want_path:
            cost, path = _dtw_path_python(a, b)
        else:
            cost = _dtw_python(_point_dist(a, b), band)
        path = path if want_path else None
    dist = float(cost) / (a.shape[0] + b.shape[0])
    return (dist, path) if want_path else dist


def discrete_frechet(a: np.ndarray, b: np.ndarray) -> float:
    """Discrete Fréchet distance (Eiter & Mannila 1994)."""
    a = np.ascontiguousarray(a, dtype=np.float64)
    b = np.ascontiguousarray(b, dtype=np.float64)
    if _HAVE_NUMBA:
        return float(_frechet_nb(a, b))
    D = _point_dist(a, b)
    na, nb = D.shape
    ca = np.empty((na, nb))
    ca[0, 0] = D[0, 0]
    for i in range(1, na):
        ca[i, 0] = max(ca[i - 1, 0], D[i, 0])
    for j in range(1, nb):
        ca[0, j] = max(ca[0, j - 1], D[0, j])
    for i in range(1, na):
        for j in range(1, nb):
            ca[i, j] = max(D[i, j], min(ca[i - 1, j], ca[i - 1, j - 1],
                                        ca[i, j - 1]))
    return float(ca[na - 1, nb - 1])


def _resample(c: np.ndarray, m: int) -> np.ndarray:
    seg = np.sqrt(np.sum(np.diff(c, axis=0) ** 2, axis=1))
    s = np.concatenate(([0.0], np.cumsum(seg)))
    if s[-1] <= 0:
        return np.repeat(c[:1], m, axis=0)
    si = np.linspace(0, s[-1], m)
    return np.stack([np.interp(si, s, c[:, 0]),
                     np.interp(si, s, c[:, 1])], axis=1)


def euclid_resampled(a: np.ndarray, b: np.ndarray, m: int = 64) -> float:
    ra, rb = _resample(a, m), _resample(b, m)
    d = ra - rb
    return float(np.sqrt(np.mean(np.sum(d * d, axis=1))))


DISTANCES = {"dtw": dtw, "frechet": discrete_frechet, "euclid": euclid_resampled}


def dist(name: str, a: np.ndarray, b: np.ndarray) -> float:
    return DISTANCES[name](a, b)


def distance_matrix(seqs: list[np.ndarray], name: str = "dtw") -> np.ndarray:
    n = len(seqs)
    M = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            M[i, j] = M[j, i] = dist(name, seqs[i], seqs[j])
    return M


def medoid(seqs: list[np.ndarray], M: np.ndarray | None = None,
           name: str = "dtw") -> int:
    if M is None:
        M = distance_matrix(seqs, name)
    return int(np.argmin(M.sum(axis=1)))


def dba(seqs: list[np.ndarray], n_iter: int = 10, *, name: str = "dtw") -> np.ndarray:
    """DTW barycenter averaging; initialized with the medoid."""
    if not seqs:
        raise ValueError("dba needs at least one sequence")
    M = distance_matrix(seqs, name)
    center = np.asarray(seqs[medoid(seqs, M, name)], dtype=float).copy()
    for _ in range(int(n_iter)):
        m = center.shape[0]
        acc = np.zeros((m, 2))
        cnt = np.zeros(m)
        for s in seqs:
            _, path = dtw(center, s, want_path=True)
            for ci, si in path:
                acc[ci] += s[si]
                cnt[ci] += 1
        valid = cnt > 0
        if not valid.any():
            break
        newc = center.copy()
        newc[valid] = acc[valid] / cnt[valid][:, None]
        # Keep the center's time axis. Resampling the averaged curve by arc
        # length would move the time coordinates and, on repeated iterations,
        # smear a sharp edge into a ramp (DBA then stops representing the
        # shape). The time axis is the local reference, not part of the
        # quantity being averaged.
        newc[:, 0] = center[:, 0]
        if np.allclose(newc, center):
            center = newc
            break
        center = newc
    return center


def require_distance_tools() -> None:
    """Kept for symmetry: distances themselves have a pure NumPy fallback."""
    require_research()
