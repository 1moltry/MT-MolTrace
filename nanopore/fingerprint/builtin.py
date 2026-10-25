"""Built-in describers: scalar features and DP+BIC piecewise-constant steps.

Both are explicit registrations (imported by :mod:`nanopore.fingerprint`), so
PyInstaller and the CLI see the same set.
"""
from __future__ import annotations

from typing import Any, Mapping

import numpy as np
from scipy.stats import kurtosis, skew

from ..params import ParamSpec
from ..steps import (AMP_MIN_PA, EDGE_K, EDGE_LEVEL_M, EDGE_SETTLE_MS,
                     EDGE_WIN, EDGE_WIN_MS, K_MAX, TAU_MIN_US, detect_steps,
                     edge_bounds, effective_sample_size, trim_exit_transition)
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
    """Split the event body into a variable number of constant steps.

    ``beta`` rather than ``stable``: on the only frozen annotation corpus
    (GalNAc-1, 12 events / 97 fingerprints) the source BIC setting
    over-segments strongly (≈195 intervals, interval F1@0.5 ms ≈ 0.15). The
    algorithm is usable and remains the default while the calibration work in
    phase 4 is evaluated further, but its output must be checked, not trusted.
    """

    id = "dp_bic"
    label = "DP+BIC 台阶"
    version = "2"
    maturity = "beta"
    input_trace = "analysis"
    params = (
        ParamSpec("k_max", K_MAX, "int", "最大段数", "DP 搜索的段数上限",
                  minimum=1, maximum=200),
        ParamSpec("tau_min_us", TAU_MIN_US, "float", "最小驻留 (µs)",
                  "短于此的段并入相邻段", minimum=10.0, maximum=5000.0),
        ParamSpec("amp_min_pA", AMP_MIN_PA, "float", "最小跃变 (pA)",
                  "相对前一段的跃变下限", minimum=0.0, maximum=500.0),
        ParamSpec("snr_min", 0.0, "float", "最小显著度（0=关）",
                  "(|amp|/σ)·√(τ·fs) 下限；本数据典型阶跃为数百，"
                  "调大能压段数但明显损失召回",
                  minimum=0.0, maximum=2000.0),
        ParamSpec("n_dp_max", 5000, "int", "DP 最大点数",
                  "超长事件先块平均降采样到该点数再跑 DP；越小越快、时间分辨率越低",
                  minimum=200, maximum=20000),
        ParamSpec("edge_win_ms", EDGE_WIN_MS, "float", "去边平滑窗 (ms)",
                  "按物理时间定义，25/50 kHz 行为一致；>0 时优先于 edge_win",
                  minimum=0.0, maximum=50.0),
        ParamSpec("edge_win", EDGE_WIN, "int", "去边平滑窗 (采样，旧参数)",
                  "仅在 edge_win_ms=0 时使用，保留旧配置语义",
                  minimum=1, maximum=51),
        ParamSpec("edge_k", EDGE_K, "float", "去边导数门限",
                  "|平滑导数| < k·σ/√win 视为稳定", minimum=0.5, maximum=20.0),
        ParamSpec("edge_settle_ms", EDGE_SETTLE_MS, "float", "去边稳定时长 (ms)",
                  "连续稳定多久才算离开过渡沿", minimum=0.0, maximum=10.0),
        ParamSpec("edge_level_m", EDGE_LEVEL_M, "float", "出孔电平门限",
                  "按事件方向判回到开孔；m·σ 为容差", minimum=0.0, maximum=20.0),
        ParamSpec("trim_exit_frac", 0.25, "float", "慢出孔尾部修剪 (×深度)",
                  "尾部段单调逼近开孔、末电平落在该比例 × 事件深度内时，"
                  "作为过渡沿剔除；0=关", minimum=0.0, maximum=1.0),
        ParamSpec("bic_penalty", 1.0, "float", "BIC 惩罚乘子",
                  ">1 抑制过分割；默认 1.0 与标定源一致", minimum=0.1, maximum=10.0),
        ParamSpec("bic_n_eff", 0, "int", "BIC 有效样本数",
                  "0=沿用降采样点数（源行为）；>0 手动指定；-1 按自相关估计",
                  minimum=-1, maximum=1000000),
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

        direction = int(getattr(view, "direction", 0) or 0)
        t_in, t_out = edge_bounds(
            body, sigma, view.fs, view.i_open,
            win_ms=float(p["edge_win_ms"]), win=int(p["edge_win"]),
            k=float(p["edge_k"]),
            settle_ms=float(p["edge_settle_ms"]), level_m=float(p["edge_level_m"]),
            direction=direction,
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
            bic_penalty=float(p["bic_penalty"]),
            bic_n_eff=float(p["bic_n_eff"]),
        )

        # The level criterion follows a slow exit to the open pore; the
        # constant-level fit can turn that ramp into a few false steps. Drop
        # the ramp and end the description at the last stable level instead.
        t_out_raw = t_out
        n_steps_raw = len(steps)
        steps = trim_exit_transition(
            steps, i_open=view.i_open, i_blockade=view.i_blockade,
            max_frac=float(p["trim_exit_frac"]))
        if steps:
            t_out = t_in + int(steps[-1].end)
            trimmed = body[t_in:t_out]

        segments: list[Segment] = []
        for st in steps:
            a = t_in + int(st.start)
            b = t_in + int(st.end)
            if b <= a:
                continue
            segments.append(Segment(
                start=a, end=b,
                level_pA=float(st.level_pA),
                level_rel=float(st.level_pA - view.i_blockade),
                level_norm=float(st.level_pA / view.i_open) if view.i_open else float("nan"),
                attrs={"amp_pA": float(st.amp_pA), "snr": float(st.snr),
                       "tau_ms": float(st.tau_s * 1e3), "decim": int(decim),
                       "n_samples": int(st.length)},
                # global coordinates: relative to the event start, then to the record
                start_global=view.start + a,
                end_global=view.start + b,
            ))

        n_eff = (effective_sample_size(trimmed)
                 if float(p["bic_n_eff"]) < 0 else float(p["bic_n_eff"]))
        covered = sum(seg.width_samples for seg in segments)
        ambiguous = bool(getattr(view, "meta", {}).get("baseline_ambiguous", False))
        quality = {"valid": True, "coverage_ms": covered / view.fs * 1000.0}
        if ambiguous:
            quality["baseline_ambiguous"] = True
            quality["reason"] = "multi-level/bidirectional body: i_blockade is a fallback"
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
                "edge_out_raw_samples": float(t_out_raw),
                "n_segments_raw": float(n_steps_raw),
                "trimmed_samples": float(trimmed.size),
                "coverage_frac": covered / max(view.n_samples, 1),
                "coverage_trimmed_frac": covered / max(trimmed.size, 1),
                "bic_n_eff": float(n_eff),
                "direction": float(direction),
            },
            payload={
                "sigma_open_pA": sigma,
                "i_open_pA": view.i_open,
                "i_blockade_pA": view.i_blockade,
                "direction": direction,
                "baseline_ambiguous": ambiguous,
                "coordinate": "segments relative to event start; levels in pA / rel / norm",
            },
            quality=quality,
        )


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Boolean mask -> half-open runs ``[(start, end), ...]``."""
    if not mask.any():
        return []
    idx = np.flatnonzero(np.diff(np.r_[0, mask.view(np.int8), 0]))
    return list(zip(idx[0::2], idx[1::2]))


def _merge_runs(intervals: list[tuple[int, int]], max_gap: int
                ) -> list[tuple[int, int]]:
    if not intervals:
        return []
    out = [list(sorted(intervals)[0])]
    for s, e in sorted(intervals)[1:]:
        if s - out[-1][1] <= max_gap:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return [(int(a), int(b)) for a, b in out]


def _open_pore_sigma(view: EventView) -> float:
    """Noise sigma from the open-pore context, not from the blocked body.

    The body can be mostly occupied by fingerprints, so its MAD overestimates
    the noise and hides weak features. The pre-event context is open pore.
    """
    i1 = max(0, view.start - view.ctx_start)
    op = np.asarray(view.current[:i1], dtype=float)
    op = op[np.isfinite(op)]
    if op.size >= 20:
        s = 1.4826 * float(np.median(np.abs(op - np.median(op))))
        if np.isfinite(s) and s > 0:
            return s
    if np.isfinite(view.sigma_open) and view.sigma_open > 0:
        return float(view.sigma_open)
    body = view.body
    body = body[np.isfinite(body)]
    if body.size < 10:
        return float("nan")
    s = 1.4826 * float(np.median(np.abs(body - np.median(body))))
    return float(s) if np.isfinite(s) and s > 0 else float("nan")


class ClassicDescriber(EventDescriber):
    """Classic dual-threshold candidate finder (the non-ML comparison arm).

    Ported from the sugar project's ``cutlab.detector``. It deliberately
    ignores event direction: a fingerprint is anything that departs from the
    body's blockade baseline, whichever side it lies on. Hysteresis (high
    threshold to seed, low threshold to extend) plus a minimum-width filter
    keeps isolated noise spikes out. Marked ``beta``: its thresholds were
    calibrated on a small annotation set and must be re-calibrated when the
    annotation corpus grows.
    """

    id = "classic"
    label = "双阈值候选（经典）"
    version = "1"
    maturity = "beta"
    input_trace = "analysis"
    params = (
        ParamSpec("thresh_sigma", 10.0, "float", "高阈 (σ)",
                  "d=|I-i_blockade|/σ 超过它才产生候选", minimum=1.0, maximum=100.0),
        ParamSpec("thresh_lo_sigma", 3.0, "float", "低阈 (σ，0=关)",
                  "候选边界向外延到低阈以下（滞回）", minimum=0.0, maximum=50.0),
        ParamSpec("smooth_ms", 0.28, "float", "平滑窗 (ms)",
                  "d(t) 的滑动平均窗；0=不平滑", minimum=0.0, maximum=20.0),
        ParamSpec("min_width_ms", 0.30, "float", "最小宽度 (ms)",
                  "短于此的候选丢弃", minimum=0.0, maximum=100.0),
        ParamSpec("merge_gap_ms", 0.20, "float", "合并间隙 (ms)",
                  "相邻候选间隙不超过它就合并", minimum=0.0, maximum=100.0),
        ParamSpec("pad_ms", 0.0, "float", "两端外扩 (ms)",
                  "候选边界额外外扩；默认 0", minimum=0.0, maximum=10.0),
    )

    def describe(self, view: EventView, params: Mapping[str, Any] | None = None
                 ) -> EventDescription:
        p = {**self.default_params(), **dict(params or {})}
        body = np.asarray(view.body, dtype=float)
        n = body.size
        if n < 3:
            return EventDescription(
                event_id=view.event_id, source=view.source,
                describer=self.id, describer_version=self.version,
                params=dict(p), quality={"valid": False, "reason": "body too short"},
            )
        i_base = float(view.i_blockade)
        sigma = _open_pore_sigma(view)
        if not np.isfinite(i_base) or not np.isfinite(sigma) or sigma <= 0:
            return EventDescription(
                event_id=view.event_id, source=view.source,
                describer=self.id, describer_version=self.version,
                params=dict(p),
                quality={"valid": False, "reason": "baseline or sigma unavailable"},
            )

        d = np.abs(body - i_base) / sigma
        smooth_n = max(1, int(round(float(p["smooth_ms"]) / 1000.0 * view.fs)))
        if smooth_n > 1:
            d = np.convolve(d, np.ones(smooth_n) / smooth_n, mode="same")

        runs = _runs(d > float(p["thresh_sigma"]))
        lo = float(p["thresh_lo_sigma"])
        if lo > 0 and runs:
            mlo = d > lo
            extended = []
            for s, e in runs:
                a = s
                while a > 0 and mlo[a - 1]:
                    a -= 1
                b = e
                while b < n and mlo[b]:
                    b += 1
                extended.append((a, b))
            runs = extended

        min_w = max(1, int(round(float(p["min_width_ms"]) / 1000.0 * view.fs)))
        max_gap = max(0, int(round(float(p["merge_gap_ms"]) / 1000.0 * view.fs)))
        pad = max(0, int(round(float(p["pad_ms"]) / 1000.0 * view.fs)))
        runs = [(s, e) for s, e in runs if (e - s) >= min_w]
        runs = _merge_runs(runs, max_gap)

        segments: list[Segment] = []
        for s, e in runs:
            a = max(0, s - pad)
            b = min(n, e + pad)
            if b <= a:
                continue
            level = float(np.median(body[a:b]))
            delta = level - i_base
            segments.append(Segment(
                start=a, end=b, level_pA=level,
                level_rel=float(level - view.i_blockade),
                level_norm=float(level / view.i_open) if view.i_open else float("nan"),
                attrs={"amp_pA": float(delta),
                       "snr": float(abs(delta) / sigma),
                       "tau_ms": float((b - a) / view.fs * 1000.0),
                       "thresh_sigma": float(p["thresh_sigma"])},
                start_global=view.start + a, end_global=view.start + b,
            ))

        covered = sum(seg.width_samples for seg in segments)
        ambiguous = bool(getattr(view, "meta", {}).get("baseline_ambiguous", False))
        quality = {"valid": True, "coverage_ms": covered / view.fs * 1000.0}
        if ambiguous:
            quality["baseline_ambiguous"] = True
            quality["reason"] = "multi-level/bidirectional body: i_blockade is a fallback"
        return EventDescription(
            event_id=view.event_id, source=view.source,
            describer=self.id, describer_version=self.version,
            params=dict(p), segments=segments,
            features={
                "n_segments": float(len(segments)),
                "coverage_frac": covered / max(view.n_samples, 1),
                "sigma_open_pA": float(sigma),
                "i_blockade_pA": float(i_base),
                "direction": float(getattr(view, "direction", 0) or 0),
            },
            payload={
                "method": "dual-threshold hysteresis on |I-i_blockade|/sigma",
                "direction_aware": False,
                "i_blockade_pA": view.i_blockade,
                "baseline_ambiguous": ambiguous,
            },
            quality=quality,
        )


register(ScalarDescriber())
register(DPBICDescriber())
register(ClassicDescriber())
