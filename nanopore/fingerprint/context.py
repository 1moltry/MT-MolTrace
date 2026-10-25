"""Build :class:`EventView` objects from the analysis result.

This is the bridge between detection and description. It is the only place
that knows how a feature-table row, the analysis trace, the raw trace, the
dynamic I0 profile and the voltage trace line up. Describers never read an ABF
and never touch Qt.

Two constructors exist:

* :func:`build_event_view` — the production path: takes an ``AnalysisResult``
  and an event index, so the view uses exactly the trace, slicing and
  open-pore reference the detector and features used.
* :func:`view_from_row` — the compatibility path for callers that only have a
  recording plus a feature row (old ``describe_rows``). It has no filtered
  trace, so ``trace_source`` is ``"raw"``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import numpy as np

from .contracts import (EFFECTIVE_BW_HZ, EventView, event_key, source_id_for_rec)


# --------------------------------------------------------------------------- #
# Reference estimators (moved verbatim from the old describe module)
# --------------------------------------------------------------------------- #

def _num(row: Mapping, key: str, default=None):
    try:
        v = row[key]
    except (KeyError, IndexError, TypeError):
        return default
    if v is None:
        return default
    try:
        if not np.isfinite(float(v)):
            return default
    except (TypeError, ValueError):
        return default
    return v


def context_pad_samples(n_samples: int, fs: float, frac: float = 0.30,
                        min_ms: float = 3.0) -> int:
    return int(round(max(min_ms, frac * (n_samples / fs) * 1000.0) / 1000.0 * fs))


def estimate_i_open(seg: np.ndarray, pct: float = 97.0) -> float:
    """Coarse open-pore current from the upper percentile (downward events)."""
    x = np.asarray(seg, dtype=float)
    x = x[np.isfinite(x)]
    return float(np.percentile(x, pct)) if x.size else float("nan")


def estimate_sigma_open(seg: np.ndarray, i_open: float,
                        depth_pA: float | None = None,
                        depth_frac: float = 0.05,
                        min_band_pA: float = 5.0) -> float:
    """Open-pore noise sigma from a narrow band around the open level.

    Taking 3*std over the whole window inflates sigma when the event body
    occupies most of it (measured 43.9 pA vs a true ~1.8 pA in the source
    project). Here only samples within max(5 pA, 5% depth) of ``i_open`` are
    used, and sigma comes from their MAD.
    """
    x = np.asarray(seg, dtype=float)
    x = x[np.isfinite(x)]
    if x.size < 10 or not np.isfinite(i_open):
        return float("nan")
    if depth_pA is None or not np.isfinite(depth_pA):
        depth_pA = abs(i_open - float(np.percentile(x, 15)))
    band = max(min_band_pA, depth_frac * abs(depth_pA))
    sel = x[np.abs(x - i_open) <= band]
    if sel.size < 10:
        k = max(10, x.size // 100)
        order = np.argsort(np.abs(x - i_open))[:k]
        sel = x[order]
    mad = np.median(np.abs(sel - np.median(sel)))
    return float(1.4826 * mad) if mad > 0 else float("nan")


def estimate_blockade_baseline(body: np.ndarray, pct: float = 15.0) -> float:
    """Blockade baseline inside the event body (low percentile, default p15)."""
    x = np.asarray(body, dtype=float)
    x = x[np.isfinite(x)]
    return float(np.percentile(x, pct)) if x.size >= 10 else float("nan")


def blockade_percentile(direction: int) -> float:
    """Blockade-side percentile for an event direction.

    Downward blockades sit below the open pore, so the blockade baseline is
    the body's p15. Upward blockades sit above it, so p85 is the matching
    statistic. Unknown/bidirectional events have no single blockade side; p15
    stays as the legacy fallback and the view is flagged as ambiguous.
    """
    return 85.0 if int(direction) > 0 else 15.0


def _direction_from_body(body: np.ndarray, i_open: float) -> int:
    """Infer direction from the body when the feature row has no signed mean."""
    x = np.asarray(body, dtype=float)
    x = x[np.isfinite(x)]
    if x.size < 10 or not np.isfinite(i_open):
        return 0
    up = float(np.percentile(x, 97)) - float(i_open)
    down = float(i_open) - float(np.percentile(x, 3))
    thr = max(1.0, 0.05 * abs(float(i_open)))
    if up > thr and down > thr:
        return 0
    if down > max(up, thr):
        return -1
    if up > max(down, thr):
        return 1
    return 0


def baseline_is_ambiguous(body: np.ndarray, i_open: float, sigma: float,
                          direction: int) -> bool:
    """True when the body has significant excursions on *both* sides.

    Such a body is bidirectional or multi-level: a single ``i_blockade`` cannot
    describe it honestly, so describers must carry a quality flag instead of
    silently forcing one baseline.
    """
    x = np.asarray(body, dtype=float)
    x = x[np.isfinite(x)]
    if x.size < 10 or not np.isfinite(i_open):
        return True
    if int(direction) == 0:
        return True
    up = float(np.percentile(x, 97)) - float(i_open)
    down = float(i_open) - float(np.percentile(x, 3))
    thr = max(3.0 * (sigma if np.isfinite(sigma) and sigma > 0 else 0.0), 1.0)
    return bool(up > thr and down > thr)


# --------------------------------------------------------------------------- #
# Shared construction
# --------------------------------------------------------------------------- #

def _event_samples(row: Mapping, fs: float, n: int) -> tuple[int, int]:
    t1 = _num(row, "t1")
    t2 = _num(row, "t2")
    if t1 is None or t2 is None:
        raise ValueError("feature row needs numeric t1 and t2")
    s = int(round(float(t1) * fs))
    e = int(round(float(t2) * fs))
    s = max(0, min(s, n - 1))
    e = max(s + 1, min(e, n))
    return s, e


def _direction_from_row(row: Mapping, i_open: float,
                        body: np.ndarray | None = None) -> int:
    mean = _num(row, "mean")
    if mean is not None and float(mean) != 0.0:
        return -1 if float(mean) < 0 else 1
    if body is not None:
        return _direction_from_body(body, i_open)
    return 0


def _slice_or_none(arr, a: int, b: int):
    if arr is None:
        return None
    x = np.asarray(arr)
    if x.size == 0:
        return None
    return x[max(0, a):min(x.size, b)]


def _assemble(*, event_id: int, source: str, source_id: str, fs: float,
              s: int, e: int, cs: int, ce: int,
              analysis: np.ndarray, raw: np.ndarray | None,
              trace_source: str, i_open: float, i_open_source: str,
              i_blockade: float, i_blockade_source: str,
              sigma: float, sigma_source: str,
              voltage, i0_window, direction: int, state: str,
              lowpass_hz, effective_bw_hz, detector_id: str,
              detector_version: str, detector_params: dict,
              analysis_params: dict, meta: dict,
              legacy_event_id: int | None) -> EventView:
    return EventView(
        event_id=int(event_id),
        source=str(source),
        fs=float(fs),
        start=int(s), end=int(e), ctx_start=int(cs), ctx_end=int(ce),
        analysis=np.asarray(analysis, dtype=float),
        raw=None if raw is None else np.asarray(raw, dtype=float),
        trace_source=trace_source if (trace_source != "raw" or raw is not None) else "analysis",
        i_open=float(i_open), i_open_source=i_open_source,
        i_blockade=float(i_blockade), i_blockade_source=i_blockade_source,
        sigma_open=float(sigma), sigma_source=sigma_source,
        lowpass_hz=lowpass_hz,
        effective_bw_hz=effective_bw_hz,
        voltage=voltage,
        i0_profile=i0_window,
        direction=int(direction),
        state=str(state),
        source_id=source_id,
        event_key=event_key(source_id, fs, s, e),
        legacy_event_id=legacy_event_id,
        detector_id=detector_id,
        detector_version=detector_version,
        detector_params=dict(detector_params or {}),
        analysis_params=dict(analysis_params or {}),
        meta=dict(meta or {}),
    )


# --------------------------------------------------------------------------- #
# Production path: AnalysisResult
# --------------------------------------------------------------------------- #

def analysis_summary(result) -> dict[str, Any]:
    """Compact provenance of the analysis configuration (JSON-able)."""
    cfg = getattr(result, "config", None)
    mods = tuple(getattr(result, "enabled_mods", ()) or ())
    out: dict[str, Any] = {
        "detector": getattr(result, "detector_id", ""),
        "anomaly_enabled": bool(getattr(result, "anomaly_enabled", False)),
        "i0_used_for_detection": bool(getattr(result, "i0_used", False)),
        "dynamic_i0": getattr(result, "i0_profile", None) is not None,
        "enabled_mods": list(mods),
    }
    if cfg is not None:
        out.update({
            "filter_lowpass_hz": (cfg.filter_lowpass_hz
                                  if "lowpass" in mods else None),
            "polarity": cfg.polarity,
            "min_toff_ms": cfg.min_toff_ms,
            "pre_event_ms": cfg.pre_event_ms,
        })
    return out


def detector_provenance(result) -> tuple[str, str, dict[str, Any]]:
    from ..registry import get_detector

    det_id = getattr(result, "detector_id", "") or "level"
    try:
        spec = get_detector(det_id)
    except KeyError:
        return det_id, "", {}
    cfg = getattr(result, "config", None)
    params = {}
    if cfg is not None:
        params = {name: getattr(cfg, name, None) for name in spec.params}
    return det_id, spec.version, params


def build_event_view(result, index: int, *, input_trace: str | None = None,
                     ctx_pad_frac: float = 0.30,
                     ctx_pad_min_ms: float = 3.0,
                     effective_bw_hz: float | None = EFFECTIVE_BW_HZ) -> EventView:
    """Build the view for kept event ``index`` (0-based) of ``result``.

    ``result`` is a :class:`nanopore.analyze.AnalysisResult`. The view uses
    ``result.filtered`` — the exact trace the detector consumed — and keeps the
    raw window alongside it. ``input_trace`` comes from the describer and
    selects which one ``view.current`` returns.
    """
    df = result.df
    if index < 0 or index >= len(df):
        raise IndexError(f"event index {index} out of range (0..{len(df) - 1})")
    rec = result.rec
    cfg = getattr(result, "config", None)
    fs = float(rec.sample_rate_hz)
    row = df.iloc[index]
    analysis_trace = np.asarray(result.filtered, dtype=float)
    raw_trace = np.asarray(rec.current, dtype=float)

    s, e = _event_samples(row, fs, len(analysis_trace))
    pad = context_pad_samples(e - s, fs, ctx_pad_frac, ctx_pad_min_ms)
    cs = max(0, s - pad)
    ce = min(len(analysis_trace), e + pad)

    analysis = analysis_trace[cs:ce]
    raw = raw_trace[cs:ce] if raw_trace.size else None

    i_open = _num(row, "Io")
    if i_open is not None:
        i_open, i_open_source = float(i_open), "feature:Io"
    else:
        i_open, i_open_source = estimate_i_open(analysis), "view:p97"

    body = analysis[max(0, s - cs):max(0, e - cs)]
    direction = _direction_from_row(row, i_open, body)
    pct = blockade_percentile(direction)
    i_blockade = estimate_blockade_baseline(body, pct)
    if np.isfinite(i_blockade):
        i_blockade_source = f"view:body_p{int(pct)}"
    else:
        i_blockade, i_blockade_source = i_open, "fallback:i_open"

    sigma = estimate_sigma_open(analysis, i_open,
                                depth_pA=abs(i_open - i_blockade))
    sigma_source = "view:open_band_mad" if np.isfinite(sigma) else "unavailable"
    ambiguous = baseline_is_ambiguous(body, i_open, sigma, direction)
    if ambiguous:
        i_blockade_source += ":ambiguous"

    voltage = _slice_or_none(getattr(rec, "protocol_voltage", None), cs, ce)
    i0_window = None
    if getattr(result, "i0_profile", None) is not None:
        i0_window = _slice_or_none(result.i0_profile.baseline, cs, ce)

    det_id, det_version, det_params = detector_provenance(result)
    mods = tuple(getattr(result, "enabled_mods", ()) or ())
    lowpass = (getattr(cfg, "filter_lowpass_hz", None)
               if (cfg is not None and "lowpass" in mods) else None)
    trace_source = input_trace or "analysis"

    meta = {
        "source_name": Path(rec.path).name if getattr(rec, "path", None) else "",
        "units": getattr(rec, "units", ""),
        "i0_used": bool(getattr(result, "i0_used", False)),
        "i0_source": getattr(result, "i0_source", ""),
        "anomaly_enabled": bool(getattr(result, "anomaly_enabled", False)),
        "legacy_event_id": index + 1,
        "direction_source": "feature:mean" if _num(row, "mean") is not None else "view:body_percentiles",
        "baseline_ambiguous": ambiguous,
    }

    return _assemble(
        event_id=index + 1, source=str(getattr(rec, "path", "")),
        source_id=source_id_for_rec(rec), fs=fs, s=s, e=e, cs=cs, ce=ce,
        analysis=analysis, raw=raw, trace_source=trace_source,
        i_open=i_open, i_open_source=i_open_source,
        i_blockade=i_blockade, i_blockade_source=i_blockade_source,
        sigma=sigma, sigma_source=sigma_source,
        voltage=voltage, i0_window=i0_window,
        direction=direction,
        state=str(_num(row, "state", "A")),
        lowpass_hz=lowpass, effective_bw_hz=effective_bw_hz,
        detector_id=det_id, detector_version=det_version,
        detector_params=det_params, analysis_params=analysis_summary(result),
        meta=meta, legacy_event_id=index + 1,
    )


# --------------------------------------------------------------------------- #
# Compatibility path: recording + feature row (raw trace only)
# --------------------------------------------------------------------------- #

def view_from_row(rec, row: Mapping, *, event_id: int = 1,
                  ctx_pad_frac: float = 0.30,
                  ctx_pad_min_ms: float = 3.0,
                  effective_bw_hz: float | None = EFFECTIVE_BW_HZ,
                  source_id: str | None = None,
                  detector_id: str = "",
                  analysis_params: dict | None = None,
                  meta: dict | None = None) -> EventView:
    """Build a view from a recording and a feature-table row.

    Kept for callers that do not have an ``AnalysisResult``; the analysis
    trace is not available here, so both traces point at the raw recording.
    """
    fs = float(rec.sample_rate_hz)
    current = np.asarray(rec.current, dtype=float)
    s, e = _event_samples(row, fs, len(current))
    pad = context_pad_samples(e - s, fs, ctx_pad_frac, ctx_pad_min_ms)
    cs = max(0, s - pad)
    ce = min(len(current), e + pad)
    seg = current[cs:ce]

    i_open = _num(row, "Io")
    if i_open is not None:
        i_open, i_open_source = float(i_open), "feature:Io"
    else:
        i_open, i_open_source = estimate_i_open(seg), "view:p97"

    body = seg[max(0, s - cs):max(0, e - cs)]
    direction = _direction_from_row(row, i_open, body)
    pct = blockade_percentile(direction)
    i_blockade = estimate_blockade_baseline(body, pct)
    if np.isfinite(i_blockade):
        i_blockade_source = f"view:body_p{int(pct)}"
    else:
        i_blockade, i_blockade_source = i_open, "fallback:i_open"
    sigma = estimate_sigma_open(seg, i_open, depth_pA=abs(i_open - i_blockade))
    sigma_source = "view:open_band_mad" if np.isfinite(sigma) else "unavailable"
    ambiguous = baseline_is_ambiguous(body, i_open, sigma, direction)
    if ambiguous:
        i_blockade_source += ":ambiguous"

    sid = source_id or source_id_for_rec(rec)
    voltage = _slice_or_none(getattr(rec, "protocol_voltage", None), cs, ce)
    meta = dict(meta or {})
    meta.setdefault("baseline_ambiguous", ambiguous)
    return _assemble(
        event_id=event_id, source=str(getattr(rec, "path", "")), source_id=sid,
        fs=fs, s=s, e=e, cs=cs, ce=ce, analysis=seg, raw=seg,
        # no analysis trace exists on this path: declare the raw trace honestly
        trace_source="raw",
        i_open=i_open, i_open_source=i_open_source,
        i_blockade=i_blockade, i_blockade_source=i_blockade_source,
        sigma=sigma, sigma_source=sigma_source,
        voltage=voltage, i0_window=None,
        direction=direction,
        state=str(_num(row, "state", "A")),
        lowpass_hz=None, effective_bw_hz=effective_bw_hz,
        detector_id=detector_id, detector_version="", detector_params={},
        analysis_params=dict(analysis_params or {}),
        meta=meta, legacy_event_id=event_id,
    )
