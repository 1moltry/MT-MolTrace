"""Platform-hysteresis event detection (ported from npsweep).

Semantics: an event is a *blockade dwell*. The boundary sits at the shallow
exit threshold (close to the open pore) while a deeper enter threshold only
validates that the run is a real blockade. Short returns to the open pore are
bridged. This keeps a long event with partial recoveries in one piece, which is
what event-internal analysis needs; the level method cuts it at the 50% crossing.

Post-filters ported with the detector:
- voltage-protocol segments are masked before detection;
- events terminated by a voltage pulse are dropped (pulse-cleared blockades);
- membrane-rupture / pore-collapse pseudo-events are dropped.

Direction is one of ``down`` / ``up`` / ``both``. ``both`` is the analogue of
the level detector's bidirectional search for peptides that blockade on either
side of the open pore.
"""

from __future__ import annotations

import numpy as np

from .detect import DetectionRejection, DetectionResult, Event


def _runs_of_bool(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    m = np.concatenate(([False], np.asarray(mask, dtype=bool), [False])).astype(np.int8)
    d = np.diff(m)
    return np.flatnonzero(d == 1), np.flatnonzero(d == -1)


def _longest_run(mask: np.ndarray) -> int:
    if not mask.any():
        return 0
    idx = np.flatnonzero(mask)
    d = np.diff(idx)
    br = np.flatnonzero(d > 1)
    st = np.concatenate(([0], br + 1))
    en = np.concatenate((br + 1, [idx.size]))
    return int(max(idx[e - 1] - idx[s] + 1 for s, e in zip(st, en)))


def _dilate(mask: np.ndarray, k: int) -> np.ndarray:
    if k <= 0 or not mask.any():
        return mask
    idx = np.flatnonzero(mask)
    d = np.diff(idx)
    starts = idx[np.concatenate(([True], d > 1))]
    ends = idx[np.concatenate((d > 1, [True]))]
    out = mask.copy()
    for s, e in zip(starts, ends):
        out[max(0, s - k): e + k + 1] = True
    return out


def build_mask(current: np.ndarray, voltage: np.ndarray | None, *,
               exclude_voltage: bool = True, voltage_tol_mv: float = 20.0,
               artifact_abs_pA: float = 1000.0,
               artifact_diff_pA: float = 500.0,
               dilate_ms: float = 2.0,
               sample_rate_hz: float = 25000.0) -> np.ndarray:
    """Mask protocol-voltage segments and current artifacts, then dilate."""
    n = len(current)
    mask = np.zeros(n, dtype=bool)
    if exclude_voltage and voltage is not None and len(voltage) == n:
        mask |= np.abs(voltage - np.median(voltage)) > voltage_tol_mv
    if artifact_abs_pA > 0 or artifact_diff_pA > 0:
        dI = np.abs(np.diff(current, prepend=current[0]))
        if artifact_abs_pA > 0:
            mask |= np.abs(current) > artifact_abs_pA
        if artifact_diff_pA > 0:
            mask |= dI > artifact_diff_pA
    return _dilate(mask, int(round(dilate_ms / 1000.0 * sample_rate_hz)))


def _voltage_pulse_intervals(voltage: np.ndarray | None, sample_rate_hz: float,
                             voltage_tol_mv: float, min_s: float = 0.1
                             ) -> list[tuple[int, int]]:
    if voltage is None or len(voltage) == 0:
        return []
    m = np.abs(voltage - np.median(voltage)) > voltage_tol_mv
    starts, ends = _runs_of_bool(m)
    k = int(round(min_s * sample_rate_hz))
    return [(int(s), int(e)) for s, e in zip(starts, ends) if (e - s) >= k]


def _local_open_ref(I, open_region, mask, level0, enter_depth, lo, hi, fallback):
    if hi <= lo:
        return fallback
    sel = open_region[lo:hi] & (~mask[lo:hi]) & (np.abs(I[lo:hi] - level0) < enter_depth)
    if int(sel.sum()) >= 10:
        return float(np.mean(I[lo:hi][sel]))
    return fallback


def _split_pulse_cleared(events: list[Event], pulse_starts: np.ndarray,
                         tol_samples: int, sample_rate_hz: float
                         ) -> tuple[list[Event], list[Event]]:
    if len(pulse_starts) == 0 or not events:
        return events, []
    keep, drop = [], []
    for ev in events:
        end_sample = int(round(ev.end_s * sample_rate_hz))
        near = bool(np.abs(pulse_starts - end_sample).min() <= tol_samples)
        (drop if near else keep).append(ev)
    return keep, drop


def _split_rupture(events: list[Event], I: np.ndarray, fs: float, *,
                   med_level: float = 0.55, deep_level: float = 0.45,
                   run_ms: float = 10.0) -> tuple[list[Event], list[Event]]:
    """Drop membrane-rupture / pore-collapse pseudo-events (current ≈ 0)."""
    if not events:
        return events, []
    min_run = max(1, int(round(run_ms / 1000.0 * fs)))
    keep, drop = [], []
    for ev in events:
        ref = ev.level0_ref_pA
        a = int(round(ev.start_s * fs))
        b = int(round(ev.end_s * fs))
        body = I[a:b]
        if not np.isfinite(ref) or ref <= 0 or body.size < 3:
            keep.append(ev)
            continue
        r = body / ref
        if np.median(r) < med_level or _longest_run(r < deep_level) >= min_run:
            drop.append(ev)
        else:
            keep.append(ev)
    return keep, drop


def _apply_thresholds(events: list[Event], depth_min: float, depth_max: float,
                      min_dwell_ms: float, dwell_max_ms: float
                      ) -> tuple[list[Event], list[Event]]:
    keep, drop = [], []
    for ev in events:
        d = abs(ev.depth_pA)
        ms = ev.dwell_s * 1000.0
        if d < depth_min or d > depth_max or ms < min_dwell_ms or ms > dwell_max_ms:
            drop.append(ev)
        else:
            keep.append(ev)
    return keep, drop


def detect_plateau(
    current: np.ndarray,
    sample_rate_hz: float,
    level0: float,
    *,
    voltage: np.ndarray | None = None,
    cutoff_hz: float | None = None,
    direction: str = "down",
    enter_depth_pA: float = 60.0,
    exit_depth_pA: float = 15.0,
    min_open_ms: float = 1.0,
    min_dwell_ms: float = 0.0,
    dwell_max_ms: float = 1e12,
    depth_min_pA: float = 0.0,
    depth_max_pA: float = 1e12,
    exclude_voltage: bool = True,
    voltage_tol_mv: float = 20.0,
    exclude_pulse_cleared: bool = True,
    pulse_tol_ms: float = 50.0,
    exclude_rupture: bool = True,
    artifact_abs_pA: float = 1000.0,
    artifact_diff_pA: float = 500.0,
) -> DetectionResult:
    """Hysteresis blockade-platform detector.

    ``direction``: ``down`` (current below the open pore), ``up``, or ``both``.
    ``enter_depth_pA`` validates that a run is a real blockade; the boundary
    itself sits at ``exit_depth_pA`` (close to the open pore), so partial
    recoveries inside one event do not split it. ``min_open_ms`` bridges short
    returns to the open pore.
    """
    I = np.asarray(current, dtype=float)
    fs = float(sample_rate_hz)
    dt = 1.0 / fs
    if direction not in ("down", "up", "both"):
        raise ValueError(f"direction must be down/up/both, got {direction!r}")

    mask = build_mask(
        I, voltage, exclude_voltage=exclude_voltage,
        voltage_tol_mv=voltage_tol_mv,
        artifact_abs_pA=artifact_abs_pA, artifact_diff_pA=artifact_diff_pA,
        sample_rate_hz=fs,
    )

    # per-side deviation from the open pore; >0 means inside a blockade
    dev_down = level0 - I
    dev_up = I - level0
    if direction == "down":
        blocked = (dev_down > exit_depth_pA) & ~mask
    elif direction == "up":
        blocked = (dev_up > exit_depth_pA) & ~mask
    else:
        blocked = ((dev_down > exit_depth_pA) | (dev_up > exit_depth_pA)) & ~mask

    starts, ends = _runs_of_bool(blocked)

    # bridge short returns to the open pore
    min_open = int(round(min_open_ms / 1000.0 * fs))
    if min_open > 1 and len(starts) > 1:
        ms, me = [int(starts[0])], [int(ends[0])]
        for s, e in zip(starts[1:], ends[1:]):
            if s - me[-1] < min_open:
                me[-1] = int(e)
            else:
                ms.append(int(s)); me.append(int(e))
        starts, ends = np.array(ms), np.array(me)

    # a run must actually reach the enter depth on at least one searched side
    keep = []
    for i in range(len(starts)):
        a, b = int(starts[i]), int(ends[i])
        if direction == "down":
            ok = dev_down[a:b].max() > enter_depth_pA
        elif direction == "up":
            ok = dev_up[a:b].max() > enter_depth_pA
        else:
            ok = (dev_down[a:b].max() > enter_depth_pA
                  or dev_up[a:b].max() > enter_depth_pA)
        if ok:
            keep.append(i)
    enter_depth_rejected = len(starts) - len(keep)
    starts = np.array([starts[i] for i in keep], dtype=int)
    ends = np.array([ends[i] for i in keep], dtype=int)

    # drop first/last partial runs (unknown extent)
    edge_skipped = 0
    if len(starts) > 2:
        starts, ends = starts[1:-1], ends[1:-1]
        edge_skipped = 2

    fc = cutoff_hz
    tau = max(0.5, (1.0 / (2.0 * np.pi * fc) * fs) if fc else 1.0)
    trim = int(round(2 * tau))
    brief_len = int(round(4 * tau))

    open_region = (dev_down < exit_depth_pA) & (dev_up < exit_depth_pA)
    base_sel = open_region & ~mask & (np.abs(I - level0) < enter_depth_pA)
    base_val = float(np.median(I[base_sel])) if base_sel.any() else float(level0)

    events: list[Event] = []
    for a, b in zip(starts, ends):
        a, b = int(a), int(b)
        dur = b - a
        if dur <= 0:
            continue
        body = I[a + trim: b - trim] if dur > trim + 2 else I[a + (dur // 2): a + (dur // 2) + 1]
        amp = float(np.mean(body))
        state = "B" if dur < brief_len else "A"

        ref = _local_open_ref(I, open_region, mask, level0, enter_depth_pA,
                              max(0, a - int(1.0 * fs)), a, base_val)
        depth = amp - ref

        events.append(Event(
            start_s=a * dt,
            end_s=b * dt,
            amplitude_pA=amp,
            depth_pA=depth,
            level0_ref_pA=ref,
            level=1,
            state=state,
        ))

    pulses = _voltage_pulse_intervals(voltage, fs, voltage_tol_mv)
    pstarts = np.array([s for s, _ in pulses], dtype=np.int64)
    rejected: list[DetectionRejection] = []
    n_pulse = n_rupture = n_threshold = 0
    if exclude_pulse_cleared and pstarts.size:
        events, dr = _split_pulse_cleared(
            events, pstarts, int(round(pulse_tol_ms / 1000.0 * fs)), fs)
        rejected += [DetectionRejection(e, "plateau:pulse_cleared") for e in dr]
        n_pulse = len(dr)
    if exclude_rupture:
        events, dr = _split_rupture(events, I, fs)
        rejected += [DetectionRejection(e, "plateau:rupture") for e in dr]
        n_rupture = len(dr)
    events, dr = _apply_thresholds(
        events, depth_min_pA, depth_max_pA, min_dwell_ms, dwell_max_ms)
    rejected += [DetectionRejection(e, "plateau:threshold") for e in dr]
    n_threshold = len(dr)

    if direction == "up":
        levels = np.array([level0, level0 + enter_depth_pA], dtype=float)
    elif direction == "down":
        levels = np.array([level0, level0 - enter_depth_pA], dtype=float)
    else:
        levels = np.array([level0, level0 - enter_depth_pA,
                           level0 + enter_depth_pA], dtype=float)
    m_starts, m_ends = _runs_of_bool(mask)
    masked_intervals = [(float(a) / fs, float(b) / fs)
                        for a, b in zip(m_starts, m_ends)]
    return DetectionResult(
        events=events,
        levels_initial=levels,
        sample_rate_hz=fs,
        level0_final=float(base_val),
        level0_refs=np.array([e.level0_ref_pA for e in events], dtype=float),
        rejected=rejected,
        masked_intervals=masked_intervals,
        diagnostics={
            "enter_depth_rejected": int(enter_depth_rejected),
            "edge_skipped": int(edge_skipped),
            "pulse_cleared": int(n_pulse),
            "rupture": int(n_rupture),
            "threshold": int(n_threshold),
            "masked_samples": int(mask.sum()),
            "masked_regions": len(masked_intervals),
        },
    )
