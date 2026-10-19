"""Threshold/level-based single-channel event detection.

Semantics implemented here:
- Nearest-level attribution: every sample belongs to the level nearest in
  amplitude; the midpoint between two levels is the 50% crossing.
- Ignore duration: a departure from the current level lasting less than
  `ignore_duration_ms` does not end the current event. Absorbed out-of-level
  samples are excluded from the event amplitude.
- Amplitude: mean of level-attributed samples excluding `2*tau` samples at
  each end (filter settling). Events shorter than `4*tau` take the midpoint
  sample amplitude and are flagged brief ("B").
- Level updating: new = (1-w)*old + w*amp with w = level_contribution scaled
  by min(1, run_len/short_len) so short runs contribute proportionally less.
  "baseline" mode moves level0 and keeps level offsets fixed; "all" updates
  every level independently.
- First/last partial events (touching the record boundaries) are ignored:
  their start/end times are unknown.

Implementation: samples are classified to levels in one vectorized pass with
the initial levels; runs are then merged/walked in order while levels update
streamingly (drift over a record is slow relative to step amplitudes, so a
single classification pass is sufficient; per-event baseline reference is
tracked for drift-corrected features).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Event:
    start_s: float
    end_s: float
    amplitude_pA: float    # absolute mean current within the event
    depth_pA: float        # signed excursion relative to baseline at event time
    level0_ref_pA: float   # baseline value used for this event (drift tracking)
    level: int             # index into the level array (0 = baseline)
    state: str = "A"       # A = accepted, B = brief

    @property
    def dwell_s(self) -> float:
        return self.end_s - self.start_s


@dataclass
class DetectionResult:
    events: list[Event]
    levels_initial: np.ndarray   # pA, level values used for classification
    sample_rate_hz: float
    level0_final: float          # baseline after the last update (drift end point)
    level0_refs: np.ndarray      # per-event baseline reference, aligned to events


def tau_samples_for(sample_rate_hz: float, cutoff_hz: float | None) -> float:
    """Filter time constant in samples. tau = 1/(2*pi*f_c); without filter info
    assume tau = 1 sample (no extra settling to trim)."""
    if cutoff_hz is None or cutoff_hz <= 0:
        return 1.0
    tau_s = 1.0 / (2.0 * np.pi * cutoff_hz)
    return max(0.5, tau_s * sample_rate_hz)


def build_levels(level0: float, level1: float, polarity: int) -> np.ndarray:
    """Level array: index 0 = baseline. polarity +1/-1 = single event level;
    0 = symmetric levels on both sides of baseline (bidirectional search)."""
    delta = abs(level1 - level0)
    if delta <= 0:
        return np.array([level0])
    if polarity > 0:
        return np.array([level0, level0 + delta])
    if polarity < 0:
        return np.array([level0, level0 - delta])
    return np.array([level0, level0 + delta, level0 - delta])


def _bridge_same_level_events(
    events: list[Event],
    ignore_ev_samples: int,
    step: float,
    dt: float,
) -> list[Event]:
    """Merge same-level events separated by a baseline blip shorter than the
    event-level ignore duration (merged-burst semantics: within one level
    class, brief returns to baseline do not end the blockade). The blip's
    samples are excluded from the merged amplitude; its time stays inside the
    merged dwell."""
    if len(events) < 2:
        return events
    out: list[Event] = [events[0]]
    ignore_gap_ms = ignore_ev_samples * dt * 1e3   # samples -> ms
    for ev in events[1:]:
        prev = out[-1]
        gap_ms = (ev.start_s - prev.end_s) * 1e3
        if not (0 <= gap_ms < ignore_gap_ms) or ev.level != prev.level:
            out.append(ev)
            continue
        # merge: extend prev across the blip; amplitude = dwell-weighted mean
        # of the segment amplitudes (blip samples excluded naturally).
        out[-1] = Event(
            start_s=prev.start_s,
            end_s=ev.end_s,
            amplitude_pA=(prev.amplitude_pA * max(prev.dwell_s, 1e-9)
                          + ev.amplitude_pA * max(ev.dwell_s, 1e-9))
                         / max(prev.dwell_s + ev.dwell_s, 1e-9),
            depth_pA=prev.depth_pA,
            level0_ref_pA=prev.level0_ref_pA,
            level=prev.level,
            state=prev.state if prev.state == ev.state else "B",
        )
    return out


def detect_events(
    current: np.ndarray,
    sample_rate_hz: float,
    level0: float,
    level1: float,
    ignore_duration_ms: float = 2.0,
    ignore_event_duration_ms: float = 50.0,
    level_contribution: float = 0.10,
    update_levels: str = "baseline",
    polarity: int = 0,
    cutoff_hz: float | None = None,
    pre_event_ms: float = 25.0,
    dwell_min_frac: float = 0.30,
    plateau_min_frac: float = 0.0,
) -> DetectionResult:
    """Single-channel search with spike rejection.

    A level transition is registered as an event only when the trace *dwells
    near a defined level*. Spikes — brief excursions that overshoot all levels
    (giant glitches) or wrong-polarity excursions — are rejected:
      1. Polarity: with polarity=±1, a run whose body mean departs from
         level0 in the wrong direction is not an event.
      2. Dwell: at least ``dwell_min_frac`` of the trimmed body samples must
         lie within ±0.5 * level_step of some integer level (0, 1, 2, ...).
         Single-sample spikes that overshoot all levels fail this check.
      3. Trim: 2*tau samples at each end of an event are excluded from the
         amplitude so filter transitions don't contaminate the body mean.
      4. Plateau (optional, ``plateau_min_frac`` > 0): the event body must
         *dwell on one level*, not oscillate between levels. Rejected when the
         fraction of body samples within +/-0.5 * step of the level nearest the
         body median falls below ``plateau_min_frac``. A fast flicker (alternating
         baseline<->event level, ~half the samples at each) passes checks 1-3
         but its plateau fraction is ~0.5, while a genuine blockade sits at
         ~1.0. Default 0 disables the gate (no behavior change); it is exposed
         as a parameter because it also removes genuine multi-level events
         (see config.event_plateau_min_frac).

    Ignore semantics: deviations out of a *baseline* run shorter than
    ``ignore_duration_ms`` are spike-rejected. Separately, same-level events
    separated by a baseline blip shorter than ``ignore_event_duration_ms`` are
    merged into one (see :func:`_bridge_same_level_events`), which keeps a
    noisy long blockade together while genuine short blockade events — whose
    inter-event gaps are long — are never swallowed.
    """
    levels = build_levels(level0, level1, polarity)
    if len(levels) < 2:
        return DetectionResult([], levels, sample_rate_hz, float(level0), np.array([]))

    n = len(current)
    dt = 1.0 / sample_rate_hz
    ignore_samples = max(1, int(round(ignore_duration_ms * 1e-3 * sample_rate_hz)))
    ignore_ev_samples = max(
        ignore_samples, int(round(ignore_event_duration_ms * 1e-3 * sample_rate_hz)))
    tau_s = tau_samples_for(sample_rate_hz, cutoff_hz)
    trim = int(round(2 * tau_s))          # samples excluded at each event end
    brief_len = int(round(4 * tau_s))     # events shorter than this are brief
    short_len = max(1, int(round(50 * tau_s)))  # "short" threshold for level-update downweighting
    step = abs(level1 - level0)
    event_sign = np.sign(level1 - level0) if polarity != 0 else 0

    # --- vectorized nearest-level classification with initial levels ---
    dist = np.abs(current[:, None] - levels[None, :])
    lvl = np.argmin(dist, axis=1).astype(np.int32)
    del dist

    # --- run-length encode ---
    change = np.flatnonzero(np.diff(lvl)) + 1
    run_starts = np.concatenate(([0], change))
    run_stops = np.concatenate((change, [n]))
    run_levels = lvl[run_starts]

    # --- merge runs with ignore-duration absorption ---
    # Sub-ignore deviation runs (either level context) are spike-rejected:
    # they never become standalone merged runs. Longer deviations become
    # their own runs/events; the bridge post-pass below then applies the
    # event-level "Ignore short level changes" semantics.
    merged: list[list[int]] = []   # [level, start, stop]
    absorbed: list[list[tuple[int, int]]] = []  # exclusion intervals per merged run
    for k in range(len(run_starts)):
        lv, s, e = int(run_levels[k]), int(run_starts[k]), int(run_stops[k])
        if merged and lv == merged[-1][0]:
            merged[-1][2] = e
            continue
        if merged:
            cur_lv = merged[-1][0]
            if (e - s) < ignore_samples:
                nxt_lv = int(run_levels[k + 1]) if k + 1 < len(run_starts) else -1
                if nxt_lv == cur_lv:
                    absorbed[-1].append((s, e))
                    continue
        merged.append([lv, s, e])
        absorbed.append([])

    # --- walk merged runs, updating levels streamingly ---
    events: list[Event] = []
    level_vals = levels.astype(np.float64).copy()
    offsets = level_vals - level_vals[0]
    level0 = float(level_vals[0])

    def run_amplitude(s: int, e: int, lv: int) -> tuple[float, str]:
        seg = current[s:e]
        m = e - s
        a = lvl[s:e] == lv
        if lv != 0 and trim > 0 and m > 2 * trim:
            body = slice(trim, m - trim)
            seg_body, a_body = seg[body], a[body]
        else:
            seg_body, a_body = seg, a
        sel = seg_body[a_body]
        if sel.size == 0:
            sel = seg_body if seg_body.size else seg
        if m < brief_len or (lv != 0 and sel.size < max(1, m // 4)):
            mid = m // 2
            return float(seg[mid]), "B"
        return float(np.mean(sel)), "A"

    def body_dwells_near_level(s: int, e: int, ref: float, min_frac: float = dwell_min_frac,
                               max_levels: int = 8) -> bool:
        """Dwell-near-level check.

        The search runs at up to 8 amplitude levels (0..8). A run is a genuine
        event only when its trimmed body sits near one of those levels:
          - the body median (relative to the local baseline) must be within
            ``max_levels`` level-steps, AND
          - at least ``min_frac`` of body samples must lie within ±0.5 * step
            of some integer level.
        Spikes fail both: a sharp overshoot has no median near a level, and a
        flat giant plateau (> 8 levels) is beyond the level range.
        """
        m = e - s
        if trim > 0 and m > 2 * trim:
            body = current[s + trim:e - trim]
        else:
            body = current[s:e]
        if body.size == 0 or step == 0:
            return True
        dev_L = (body - ref) / step
        if abs(float(np.median(dev_L))) > max_levels:
            return False
        nearest_L = np.round(dev_L)
        frac = float(np.mean(np.abs(dev_L - nearest_L) < 0.5))
        return frac >= min_frac

    def body_plateau_frac(s: int, e: int, ref: float) -> float:
        """Fraction of the body that dwells on ONE level (the integer level
        nearest the body median), relative to ``ref``. ~1.0 for a flat blockade,
        ~0.5 for a flicker that alternates between two levels."""
        if step == 0:
            return 1.0
        body = current[s:e]
        if body.size == 0:
            return 0.0
        dev_L = (body - ref) / step
        nearest_L = np.round(float(np.median(dev_L)))
        return float(np.mean(np.abs(dev_L - nearest_L) < 0.5))

    for idx, (lv, s, e) in enumerate(merged):
        amp, state = run_amplitude(s, e, lv)
        m = e - s
        w = level_contribution * min(1.0, m / short_len)
        if lv == 0:
            # guard: only follow baseline runs whose amplitude sits close to
            # the current baseline (0.15 step). Runs further away are
            # misclassified excursions (above/below-baseline noise
            # populations); following them ratchets level0 onto the wrong
            # level and flips baseline samples to "event". The band is tight
            # because each update is incremental (w<=0.1), so genuine slow
            # drift still tracks fine.
            if step == 0 or abs(amp - level0) <= 0.15 * step:
                level0 = (1 - w) * level0 + w * amp
                if update_levels == "baseline":
                    level_vals = level0 + offsets
                else:
                    level_vals[0] = level0
        else:
            if update_levels == "all":
                level_vals[lv] = (1 - w) * level_vals[lv] + w * amp
            # record only interior runs (first/last partial events ignored)
            if s > 0 and e < n:
                # per-event open-pore reference: mean of the last pre_event_ms
                # of the preceding baseline run, i.e. the current read just
                # before each event (drift-following)
                if idx > 0 and merged[idx - 1][0] == 0:
                    ps, pe = merged[idx - 1][1], merged[idx - 1][2]
                    w0 = int(round(pre_event_ms * 1e-3 * sample_rate_hz))
                    local0 = float(np.mean(current[max(ps, pe - w0):pe]))
                else:
                    local0 = level0
                depth = amp - local0
                # --- spike rejection ---
                # (a) polarity: with unipolar search, depth must go the way
                #     level1 indicates. Wrong-sign excursions are spikes.
                if event_sign != 0 and np.sign(depth) == -event_sign:
                    continue
                # (b) dwell-near-level: an event is registered only when the
                #     trace settles at a defined level (L=1, 2, 3...).
                #     Single-sample spikes that overshoot all levels fail.
                if step > 0 and not body_dwells_near_level(s, e, local0):
                    continue
                # (c) plateau: dwell on a single level rather than oscillate
                #     across levels (flicker). Off when plateau_min_frac == 0.
                if plateau_min_frac > 0 and body_plateau_frac(s, e, local0) < plateau_min_frac:
                    continue
                events.append(
                    Event(
                        start_s=s * dt,
                        end_s=e * dt,
                        amplitude_pA=amp,
                        depth_pA=depth,
                        level0_ref_pA=local0,
                        level=lv,
                        state=state,
                    )
                )

    # --- post-pass: bridge same-level events across short baseline blips ---
    # The merge loop above only suppresses spurious short runs (spike
    # rejection); a blip that reaches baseline still splits a long blockade
    # into many events. Bridge consecutive events of the same level whose
    # baseline gap is shorter than ignore_event_duration_ms, so a noisy
    # blockade reads as one event while genuine short events (long gaps) stay
    # separate.
    if ignore_ev_samples > ignore_samples:
        events = _bridge_same_level_events(
            events, ignore_ev_samples, step, dt,
        )

    level0_refs = np.array([ev.level0_ref_pA for ev in events])
    return DetectionResult(
        events=events,
        levels_initial=levels,
        sample_rate_hz=sample_rate_hz,
        level0_final=level0,
        level0_refs=level0_refs,
    )


# ---------------------------------------------------------------------------
# Dwell-envelope burst detector (event_mode="burst")
# ---------------------------------------------------------------------------

def _runs_of(mask: np.ndarray, value: bool) -> list[tuple[int, int]]:
    """Maximal runs where ``mask == value`` as half-open (start, stop) pairs."""
    m = np.asarray(mask, dtype=bool) == value
    if m.size == 0:
        return []
    change = np.flatnonzero(np.diff(m.astype(np.int8))) + 1
    starts = np.concatenate(([0], change))
    stops = np.concatenate((change, [m.size]))
    return [(int(s), int(e)) for s, e in zip(starts, stops) if m[s]]


def _fill_short_gaps(blocked: np.ndarray, max_len: int) -> np.ndarray:
    """Set False runs shorter than ``max_len`` to True (morphological closing)."""
    out = blocked.copy()
    if max_len > 0:
        for s, e in _runs_of(out, False):
            if (e - s) < max_len:
                out[s:e] = True
    return out


def _drop_short_blocks(blocked: np.ndarray, max_len: int) -> np.ndarray:
    """Set True runs shorter than ``max_len`` to False (morphological opening)."""
    out = blocked.copy()
    if max_len > 0:
        for s, e in _runs_of(out, True):
            if (e - s) < max_len:
                out[s:e] = False
    return out


def detect_events_burst(
    current: np.ndarray,
    sample_rate_hz: float,
    level0: float,
    level1: float,
    polarity: int = 0,
    *,
    cutoff_hz: float | None = None,
    pre_event_ms: float = 25.0,
    enter_frac: float = 0.30,
    exit_frac: float = 0.20,
    min_gap_ms: float = 30.0,
    min_block_ms: float = 2.0,
    cross_baseline: bool = False,
    baseline: np.ndarray | None = None,
) -> DetectionResult:
    """Dwell-envelope debounce: one blockade dwell = one event.

    Instead of classifying every sample to a level and treating non-baseline
    runs as events, build a *blockade indicator* from the distance to the
    open-pore level, then debounce that boolean:

      1. blocked(t) = departure from ``level0`` beyond ``enter_frac * step``.
         One side per ``polarity``; both sides when ``polarity == 0`` or
         ``cross_baseline`` is set (multi-level / baseline-crossing signals).
      2. fill non-blocked gaps shorter than ``min_gap_ms`` — absorbs brief
         returns to, or overshoots past, the open pore, so one dwell is not
         cut into pieces; also merges a baseline-hopping burst.
      3. drop blocked fragments shorter than ``min_block_ms`` — a lone spike
         does not create an event.
      4. each surviving blocked run is one event; its level is the median of
         samples beyond ``exit_frac * step`` on the dominant side.

    ``min_gap_ms`` is the burst-grouping threshold: smaller splits a burst into
    one event per opening; larger merges more excursions. Events touching the
    record boundaries are ignored (unknown extent), as in :func:`detect_events`.
    """
    levels = build_levels(level0, level1, polarity)
    step = abs(level1 - level0)
    if step <= 0:
        return DetectionResult([], levels, sample_rate_hz, float(level0), np.array([]))

    n = len(current)
    dt = 1.0 / sample_rate_hz
    tau_s = tau_samples_for(sample_rate_hz, cutoff_hz)
    trim = int(round(2 * tau_s))
    brief_len = int(round(4 * tau_s))
    pre_n = int(round(pre_event_ms * 1e-3 * sample_rate_hz))
    enter = enter_frac * step
    exit_ = exit_frac * step
    min_gap_n = max(1, int(round(min_gap_ms * 1e-3 * sample_rate_hz)))
    min_block_n = max(1, int(round(min_block_ms * 1e-3 * sample_rate_hz)))

    # reference open-pore current per sample: a dynamic baseline when supplied
    # (follows pore-state switches / drift), else the constant level0
    ref = baseline if baseline is not None else np.full(n, float(level0))
    d = current - ref
    use_both = polarity == 0 or cross_baseline
    sign = 0.0 if use_both else (1.0 if level1 > level0 else -1.0)
    blocked = np.abs(d) > enter if use_both else (sign * d) > enter

    blocked = _fill_short_gaps(blocked, min_gap_n)
    blocked = _drop_short_blocks(blocked, min_block_n)

    events: list[Event] = []
    for s, e in _runs_of(blocked, True):
        if s == 0 or e == n:          # touches a record boundary: extent unknown
            continue
        m = e - s
        if trim > 0 and m > 2 * trim:
            body, bd = current[s + trim:e - trim], d[s + trim:e - trim]
        else:
            body, bd = current[s:e], d[s:e]
        if body.size == 0:
            continue

        if use_both:
            below, above = bd < -exit_, bd > exit_
            if below.any() and int(below.sum()) >= int(above.sum()):
                sel = body[below]
            elif above.any():
                sel = body[above]
            else:
                sel = body
        else:
            sel = body[sign * bd > exit_]
            if sel.size == 0:
                sel = body
        amp = float(np.median(sel))
        local0 = float(np.median(ref[max(0, s - pre_n):s])) if s > 0 else float(ref[s])
        depth = amp - local0
        level = int(np.clip(round(depth / step), -8, 8))
        state = "B" if m < brief_len else "A"
        events.append(Event(
            start_s=s * dt,
            end_s=e * dt,
            amplitude_pA=amp,
            depth_pA=depth,
            level0_ref_pA=local0,
            level=level,
            state=state,
        ))

    level0_refs = np.array([ev.level0_ref_pA for ev in events])
    return DetectionResult(events, levels, sample_rate_hz, float(level0), level0_refs)


def detect(current: np.ndarray, sample_rate_hz: float, lv, cfg, *,
           cutoff_hz: float | None = None, i0_profile=None) -> DetectionResult:
    """Dispatch on ``cfg.event_mode``.

    ``lv`` is duck-typed (needs ``.level0`` / ``.level1`` / ``.polarity``), so
    both the pipeline and the GUI worker share one entry point and can never
    drift on parameter wiring. ``i0_profile`` (optional) gives burst mode a
    per-sample open-pore reference so pore-state switches are not mistaken for
    blockades.
    """
    cutoff = cutoff_hz if cutoff_hz is not None else cfg.filter_lowpass_hz
    if getattr(cfg, "event_mode", "level") == "burst":
        return detect_events_burst(
            current, sample_rate_hz, lv.level0, lv.level1, lv.polarity,
            cutoff_hz=cutoff,
            pre_event_ms=cfg.pre_event_ms,
            enter_frac=cfg.burst_enter_frac,
            exit_frac=cfg.burst_exit_frac,
            min_gap_ms=cfg.burst_min_gap_ms,
            min_block_ms=cfg.burst_min_block_ms,
            cross_baseline=cfg.burst_cross_baseline,
            baseline=i0_profile.baseline if i0_profile is not None else None,
        )
    return detect_events(
        current, sample_rate_hz, lv.level0, lv.level1,
        ignore_duration_ms=cfg.ignore_duration_ms,
        ignore_event_duration_ms=cfg.ignore_event_duration_ms,
        level_contribution=cfg.level_contribution,
        update_levels=cfg.update_levels,
        polarity=lv.polarity,
        cutoff_hz=cutoff,
        pre_event_ms=cfg.pre_event_ms,
        dwell_min_frac=cfg.dwell_min_frac,
        plateau_min_frac=cfg.event_plateau_min_frac,
    )
