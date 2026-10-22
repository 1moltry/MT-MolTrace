"""Single-event description layer: what an event looks like inside.

Ported from the sugar-sequencing project ``npsweep/describe.py`` (2026-10-22)
and adapted to MOLTRACE's recording/feature-table objects. The detection layer
answers "where is an event"; this layer answers "how is it structured inside".

Contracts (unchanged from the source):

* variable-length segment lists; no fixed number or width is assumed;
* describers implement :class:`EventDescriber` and register by id, so new
  methods (PELT, shape vocabulary, DTW, CNN) never touch detection or the GUI;
* ``Segment.start/end`` are sample offsets from the event start (half-open),
  so re-describing with a different context window keeps coordinates stable;
* the view carries the context window, sample rate, open-pore current, blockade
  baseline and noise sigma, so any describer can re-run without the ABF.

Coordinate note: the GUI's event selection uses 1-based event numbers, so
``EventDescription.event_id`` is 1-based and matches the table row number.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

import numpy as np
from scipy.stats import kurtosis, skew

from .steps import (AMP_MIN_PA, EDGE_K, EDGE_LEVEL_M, EDGE_SETTLE_MS, EDGE_WIN,
                    K_MAX, TAU_MIN_US, detect_steps, edge_bounds)

#: Effective bandwidth measured on the old projects' PSD; a hint only.
EFFECTIVE_BW_HZ = 1200.0


@dataclass
class EventView:
    """Read-only view of one event plus its context window."""

    event_id: int
    source: str
    fs: float
    start: int                  # event start, global samples (inclusive)
    end: int                    # event end, global samples (exclusive)
    ctx_start: int              # context window start, global samples
    ctx_end: int                # context window end, global samples
    current: np.ndarray         # context-window current (pA)
    i_open: float               # open-pore current (pA)
    i_blockade: float           # blockade baseline inside the body (pA)
    sigma_open: float           # open-pore noise sigma (pA)
    lowpass_hz: float | None = None
    effective_bw_hz: float | None = EFFECTIVE_BW_HZ
    voltage: np.ndarray | None = None
    i0_profile: np.ndarray | None = None
    state: str = "A"
    meta: dict[str, Any] = field(default_factory=dict)

    def _rel(self, a: int, b: int) -> slice:
        return slice(max(0, a - self.ctx_start), min(len(self.current), b - self.ctx_start))

    @property
    def body(self) -> np.ndarray:
        """Current inside the event body (no context padding)."""
        return self.current[self._rel(self.start, self.end)]

    @property
    def body_rel(self) -> np.ndarray:
        """Body current relative to the blockade baseline."""
        return self.body - self.i_blockade

    @property
    def body_norm(self) -> np.ndarray:
        """Body current normalized by the open-pore current."""
        if not np.isfinite(self.i_open) or self.i_open == 0:
            return self.body.copy()
        return self.body / self.i_open

    @property
    def t_rel_s(self) -> np.ndarray:
        """Context-window time (s), t=0 at the event start."""
        return (np.arange(self.ctx_start, self.ctx_end) - self.start) / self.fs

    @property
    def n_samples(self) -> int:
        return max(0, self.end - self.start)

    @property
    def duration_ms(self) -> float:
        return self.n_samples / self.fs * 1000.0

    @property
    def time_floor_ms(self) -> float | None:
        """Resolution hint: 3/(2*pi*f_eff) in ms; not a gate."""
        if not self.effective_bw_hz:
            return None
        return 1000.0 * 3.0 / (2.0 * np.pi * self.effective_bw_hz)


@dataclass
class Segment:
    """One sub-structure inside an event (a step, shape or fingerprint)."""

    start: int
    end: int
    level_pA: float | None = None
    level_rel: float | None = None      # level_pA - i_blockade
    level_norm: float | None = None     # level_pA / i_open
    attrs: dict[str, Any] = field(default_factory=dict)

    @property
    def width_samples(self) -> int:
        return max(0, self.end - self.start)


@dataclass
class EventDescription:
    """A describer's full output for one event."""

    event_id: int
    source: str
    describer: str
    describer_version: str = "1"
    params: dict[str, Any] = field(default_factory=dict)
    segments: list[Segment] = field(default_factory=list)
    features: dict[str, float] = field(default_factory=dict)
    payload: dict[str, Any] = field(default_factory=dict)
    quality: dict[str, Any] = field(default_factory=dict)
    schema_version: str = "1.0"


@dataclass(frozen=True)
class ParamSpec:
    """Declarative parameter metadata for GUI/CLI generation (Qt-free)."""

    name: str
    default: Any
    kind: str = "float"            # float / int / bool / str / choice
    label: str = ""
    desc: str = ""
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[str, ...] = ()


class EventDescriber:
    """Base class: set metadata and implement :meth:`describe`."""

    id: str = ""
    label: str = ""
    version: str = "1"
    params: tuple[ParamSpec, ...] = ()

    def default_params(self) -> dict[str, Any]:
        return {p.name: p.default for p in self.params}

    def describe(self, view: EventView, params: Mapping[str, Any] | None = None
                 ) -> EventDescription:
        raise NotImplementedError


_DESCRIBERS: dict[str, EventDescriber] = {}


def register(describer: EventDescriber) -> EventDescriber:
    if not describer.id:
        raise ValueError("describer.id must be non-empty")
    _DESCRIBERS[describer.id] = describer
    return describer


def get_describer(describer_id: str) -> EventDescriber:
    try:
        return _DESCRIBERS[describer_id]
    except KeyError:
        raise KeyError(
            f"unknown describer {describer_id!r}; available: "
            + ", ".join(sorted(_DESCRIBERS))
        ) from None


def list_describers() -> list[EventDescriber]:
    return [_DESCRIBERS[k] for k in sorted(_DESCRIBERS)]


# --------------------------------------------------------------------------- #
# View construction from MOLTRACE objects
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


def _context_pad(n_samples: int, fs: float, frac: float = 0.30,
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


def make_event_view(rec, row: Mapping, *, event_id: int = 1,
                    ctx_pad_frac: float = 0.30, ctx_pad_min_ms: float = 3.0,
                    effective_bw_hz: float | None = EFFECTIVE_BW_HZ) -> EventView:
    """Build an :class:`EventView` from a recording and a feature-table row.

    ``row`` must carry ``t1`` and ``t2`` (seconds); ``Io`` and ``state`` are
    used when present. This is the MOLTRACE counterpart of the source
    project's ``make_event_view``.
    """
    fs = float(rec.sample_rate_hz)
    t1 = _num(row, "t1")
    t2 = _num(row, "t2")
    if t1 is None or t2 is None:
        raise ValueError("feature row needs numeric t1 and t2")
    current = np.asarray(rec.current, dtype=float)
    s = int(round(float(t1) * fs))
    e = int(round(float(t2) * fs))
    s = max(0, min(s, len(current) - 1))
    e = max(s + 1, min(e, len(current)))
    pad = _context_pad(e - s, fs, ctx_pad_frac, ctx_pad_min_ms)
    cs = max(0, s - pad)
    ce = min(len(current), e + pad)
    seg = current[cs:ce]

    i_open = _num(row, "Io")
    i_open = float(i_open) if i_open is not None else estimate_i_open(seg)
    body = seg[max(0, s - cs):max(0, e - cs)]
    i_blockade = estimate_blockade_baseline(body)
    if not np.isfinite(i_blockade):
        i_blockade = i_open
    sigma = estimate_sigma_open(seg, i_open, depth_pA=abs(i_open - i_blockade))

    return EventView(
        event_id=int(event_id),
        source=str(getattr(rec, "path", "")),
        fs=fs, start=s, end=e, ctx_start=cs, ctx_end=ce,
        current=seg, i_open=i_open, i_blockade=i_blockade, sigma_open=sigma,
        effective_bw_hz=effective_bw_hz,
        state=str(_num(row, "state", "A")),
    )


def describe_rows(df, rec, cfg) -> list[EventDescription]:
    """Describe every kept event in ``df`` with ``cfg.describer``."""
    describer = get_describer(cfg.describer or "dp_bic")
    params = {**describer.default_params(), **dict(cfg.describe_params or {})}
    out: list[EventDescription] = []
    for i, (_, row) in enumerate(df.iterrows(), start=1):
        out.append(describer.describe(make_event_view(rec, row, event_id=i), params))
    return out


# --------------------------------------------------------------------------- #
# Built-in describer 1: scalar features (no segmentation)
# --------------------------------------------------------------------------- #

class ScalarDescriber(EventDescriber):
    """Whole-event scalar description; the non-structured baseline."""

    id = "scalar"
    label = "标量特征"
    version = "1"
    params = (
        ParamSpec("outlier_sigma", 3.0, "float", "离群阈值",
                  "|x - median| > k*MAD 视为离群", minimum=0.5, maximum=10.0),
    )

    def describe(self, view: EventView, params: Mapping[str, Any] | None = None
                 ) -> EventDescription:
        p = {**self.default_params(), **dict(params or {})}
        body = view.body
        body = body[np.isfinite(body)]
        if body.size < 3:
            return EventDescription(
                event_id=view.event_id, source=view.source,
                describer=self.id, describer_version=self.version,
                params=dict(p), features={"n_samples": float(body.size)},
                quality={"valid": False, "reason": "body too short"},
            )
        med = float(np.median(body))
        mad = float(np.median(np.abs(body - med)))
        q1, q2, q3 = (float(v) for v in np.percentile(body, [25, 50, 75]))
        sd = float(np.std(body))
        features = {
            "n_samples": float(body.size),
            "dwell_ms": view.duration_ms,
            "mean_pA": float(np.mean(body)),
            "median_pA": med,
            "sd_pA": sd,
            "cv": sd / abs(float(np.mean(body))) if np.mean(body) != 0 else float("nan"),
            "skew_biased": float(skew(body, bias=True)),
            "kurtosis_fisher_biased": float(kurtosis(body, fisher=True, bias=True)),
            "q1_pA": q1, "q2_pA": q2, "q3_pA": q3,
            "iqr_pA": q3 - q1,
            "depth_pA": med - view.i_open,
            "depth_norm": (med - view.i_open) / view.i_open if view.i_open else float("nan"),
            "level_blockade_pA": view.i_blockade,
            "level_blockade_norm": view.i_blockade / view.i_open if view.i_open else float("nan"),
            "outlier_ratio": (float(np.mean(np.abs(body - med) > p["outlier_sigma"] * mad))
                              if mad > 0 else 0.0),
        }
        return EventDescription(
            event_id=view.event_id, source=view.source,
            describer=self.id, describer_version=self.version,
            params=dict(p), features=features,
            payload={"coordinate": {"baseline": "i_blockade", "i_open_pA": view.i_open}},
            quality={"valid": True, "coverage_ms": view.duration_ms},
        )


# --------------------------------------------------------------------------- #
# Built-in describer 2: DP + BIC piecewise-constant steps
# --------------------------------------------------------------------------- #

class DPBICDescriber(EventDescriber):
    """Split the event body into a variable number of constant steps."""

    id = "dp_bic"
    label = "DP+BIC 台阶"
    version = "1"
    params = (
        ParamSpec("k_max", K_MAX, "int", "最大段数", "DP 搜索的段数上限",
                  minimum=1, maximum=200),
        ParamSpec("tau_min_us", TAU_MIN_US, "float", "最小驻留 (µs)",
                  "短于此的段并入相邻段", minimum=10.0, maximum=5000.0),
        ParamSpec("amp_min_pA", AMP_MIN_PA, "float", "最小跃变 (pA)",
                  "相对前一段的跃变下限", minimum=0.0, maximum=500.0),
        ParamSpec("snr_min", 0.0, "float", "最小显著度（0=关）",
                  "(|amp|/σ)·√(τ·fs) 下限；源实现未启用，默认保持一致",
                  minimum=0.0, maximum=50.0),
        ParamSpec("n_dp_max", 5000, "int", "DP 最大点数",
                  "超长事件先块平均降采样到该点数再跑 DP；越小越快、时间分辨率越低",
                  minimum=200, maximum=20000),
        ParamSpec("edge_win", EDGE_WIN, "int", "去边平滑窗 (采样)",
                  "导数法去进孔沿的平滑窗", minimum=1, maximum=51),
        ParamSpec("edge_k", EDGE_K, "float", "去边导数门限",
                  "|平滑导数| < k·σ/√win 视为稳定", minimum=0.5, maximum=20.0),
        ParamSpec("edge_settle_ms", EDGE_SETTLE_MS, "float", "去边稳定时长 (ms)",
                  "连续稳定多久才算离开过渡沿", minimum=0.0, maximum=10.0),
        ParamSpec("edge_level_m", EDGE_LEVEL_M, "float", "出孔电平门限",
                  "平滑电流 < i_open - m·σ 视为仍在阻孔内", minimum=0.0, maximum=20.0),
    )

    def describe(self, view: EventView, params: Mapping[str, Any] | None = None
                 ) -> EventDescription:
        p = {**self.default_params(), **dict(params or {})}
        body = view.body
        sigma = view.sigma_open if np.isfinite(view.sigma_open) and view.sigma_open > 0 else 1.0
        if body.size <= 3:
            return EventDescription(
                event_id=view.event_id, source=view.source,
                describer=self.id, describer_version=self.version,
                params=dict(p), quality={"valid": False, "reason": "body too short"},
            )

        t_in, t_out = edge_bounds(
            body, sigma, view.fs, view.i_open,
            win=int(p["edge_win"]), k=float(p["edge_k"]),
            settle_ms=float(p["edge_settle_ms"]), level_m=float(p["edge_level_m"]),
        )
        trimmed = body[t_in:t_out]
        if trimmed.size <= 2:
            return EventDescription(
                event_id=view.event_id, source=view.source,
                describer=self.id, describer_version=self.version,
                params=dict(p), payload={"t_in": t_in, "t_out": t_out},
                quality={"valid": False, "reason": "trimmed body too short"},
            )

        steps, k_bic, decim = detect_steps(
            trimmed, view.fs, view.i_open, sigma_pA=sigma,
            k_max=int(p["k_max"]), tau_min_us=float(p["tau_min_us"]),
            amp_min=float(p["amp_min_pA"]), snr_min=float(p["snr_min"]),
            n_dp_max=int(p["n_dp_max"]),
        )

        bounds = np.round(np.concatenate(
            ([0.0], np.cumsum([st.tau_s * view.fs for st in steps])))).astype(int)
        bounds = np.clip(bounds, 0, t_out - t_in)
        segments: list[Segment] = []
        for i, st in enumerate(steps):
            a = t_in + int(bounds[i])
            b = t_in + int(bounds[i + 1] if i + 1 < len(bounds) else bounds[-1])
            if b <= a:
                continue
            segments.append(Segment(
                start=a, end=b,
                level_pA=float(st.level_pA),
                level_rel=float(st.level_pA - view.i_blockade),
                level_norm=float(st.level_pA / view.i_open) if view.i_open else float("nan"),
                attrs={"amp_pA": float(st.amp_pA), "snr": float(st.snr),
                       "tau_ms": float(st.tau_s * 1e3), "decim": int(decim)},
            ))

        covered = sum(seg.width_samples for seg in segments)
        return EventDescription(
            event_id=view.event_id, source=view.source,
            describer=self.id, describer_version=self.version,
            params=dict(p),
            segments=segments,
            features={
                "n_segments": float(len(segments)),
                "k_bic": float(k_bic),
                "edge_in_samples": float(t_in),
                "edge_out_samples": float(t_out),
                "coverage_frac": covered / max(view.n_samples, 1),
            },
            payload={
                "sigma_open_pA": sigma,
                "i_open_pA": view.i_open,
                "i_blockade_pA": view.i_blockade,
                "coordinate": "segments relative to event start; levels in pA / rel / norm",
            },
            quality={"valid": True, "coverage_ms": covered / view.fs * 1000.0},
        )


register(ScalarDescriber())
register(DPBICDescriber())


# --------------------------------------------------------------------------- #
# Serialization
# --------------------------------------------------------------------------- #

def to_json(desc: EventDescription) -> dict:
    """Full nested structure; payload keeps arbitrary nesting."""
    return {
        "event_id": desc.event_id,
        "source": desc.source,
        "describer": desc.describer,
        "describer_version": desc.describer_version,
        "schema_version": desc.schema_version,
        "params": desc.params,
        "features": desc.features,
        "quality": desc.quality,
        "payload": desc.payload,
        "segments": [
            {"start": s.start, "end": s.end, "level_pA": s.level_pA,
             "level_rel": s.level_rel, "level_norm": s.level_norm, "attrs": s.attrs}
            for s in desc.segments
        ],
    }


def descriptions_to_json(descs: Iterable[EventDescription], source: str) -> dict:
    descs = list(descs)
    first = descs[0] if descs else None
    return {
        "schema_version": "1.0",
        "source": source,
        "describer": first.describer if first else "",
        "describer_version": first.describer_version if first else "",
        "params": first.params if first else {},
        "events": [to_json(d) for d in descs],
    }


def dumps(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=1, default=float)
