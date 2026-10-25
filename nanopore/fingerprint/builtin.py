"""Built-in describers: scalar features and DP+BIC piecewise-constant steps.

Both are explicit registrations (imported by :mod:`nanopore.fingerprint`), so
PyInstaller and the CLI see the same set.
"""
from __future__ import annotations

from typing import Any, Mapping

import numpy as np
from scipy.stats import kurtosis, skew

from ..params import ParamSpec
from ..steps import (AMP_MIN_PA, EDGE_K, EDGE_LEVEL_M, EDGE_SETTLE_MS, EDGE_WIN,
                     K_MAX, TAU_MIN_US, detect_steps, edge_bounds)
from .contracts import EventDescription, EventView, Segment
from .registry import EventDescriber, register


class ScalarDescriber(EventDescriber):
    """Whole-event scalar description; the non-structured baseline."""

    id = "scalar"
    label = "标量特征"
    version = "1"
    maturity = "stable"
    input_trace = "analysis"
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


class DPBICDescriber(EventDescriber):
    """Split the event body into a variable number of constant steps."""

    id = "dp_bic"
    label = "DP+BIC 台阶"
    version = "1"
    maturity = "stable"
    input_trace = "analysis"
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
                # global coordinates: relative to the event start, then to the record
                start_global=view.start + a,
                end_global=view.start + b,
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
