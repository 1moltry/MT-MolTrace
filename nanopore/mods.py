"""Optional feature modules: a declarative registry shared by the pipeline, the
CLI and the GUI.

A *mod* is an orthogonal processing stage or output — lowpass filtering, the
dynamic open-pore baseline, anomaly detection, the output figures, the combined
training table, the batch summary. The **base** pipeline always runs:

    read -> level estimation -> event detection -> feature extraction -> events table

Detection *variants* are **not** mods — they are plain parameters that change
how the base detector works: ``polarity``, ``event_mode`` (``level``/``burst``),
``event_plateau_min_frac`` (glitch gate), ``ignore_duration_ms`` and friends.

Add a feature by adding one :class:`ModSpec` here; the GUI renders a checkbox
from it and the CLI resolves ids through :func:`resolve_mods`.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass


@dataclass(frozen=True)
class ModSpec:
    id: str
    label: str                     # Chinese display name (GUI)
    desc: str                      # one-line description (GUI tooltip)
    default_on: bool = False       # initial checkbox state on a fresh install
    requires: tuple[str, ...] = ()  # prerequisite mod ids
    params: tuple[str, ...] = ()    # PipelineConfig fields this mod consumes


ORDER: tuple[str, ...] = (
    "lowpass",
    "dynamic_i0",
    "anomaly",
    "refined_anomaly",
    "plots",
    "waveform_export",
    "dataset_export",
    "summary",
)

MODS: dict[str, ModSpec] = {m.id: m for m in (
    ModSpec(
        "lowpass", "低通滤波",
        "检测前做零相位低通（需在参数里设截止频率；0=不比滤波）",
        params=("filter_lowpass_hz",),
    ),
    ModSpec(
        "dynamic_i0", "动态开孔基线",
        "逐事件 Io 跟随开孔电流漂移，免疫长阻孔被误当开孔",
        params=("dr_pA",),
    ),
    ModSpec(
        "anomaly", "异常检测（宏）",
        "反压/膜抖/炸膜/慢漂移区间，并剔除落在其中的事件",
        params=("jump_min_ms", "noise_sigma_mult", "jitter_min_ms",
                "refined_jitter_level_frac_max"),
    ),
    ModSpec(
        "refined_anomaly", "异常检测（细粒度）",
        "分级异常判据：反压恢复（spontaneous/manual）、轻/重膜抖、炸膜",
        requires=("anomaly", "dynamic_i0"),
        params=(
            "refined_jitter_window_ms", "refined_jitter_mild_ratio",
            "refined_jitter_severe_ratio", "refined_jitter_osc_floor",
            "refined_blockage_min_ms", "refined_blockage_fraction",
            "refined_rupture_iqr_min_pA", "refined_rupture_noise_min_ratio",
            "refined_rupture_level_frac_max",
            "refined_drift_enabled", "refined_drift_block_s", "refined_drift_min_s",
            "refined_drift_min_frac", "refined_drift_iqr_ratio",
            "refined_drift_step_pA", "refined_drift_rupture_ratio",
        ),
    ),
    ModSpec("plots", "输出图", "overview / scatter / hist 三张 PNG"),
    ModSpec("waveform_export", "事件波形导出",
            "每个保留事件的原始电流序列 → <name>_events.mat"),
    ModSpec("dataset_export", "合并训练表",
            "所有文件的保留事件纵向拼接（dataset_all.csv）"),
    ModSpec("summary", "批次汇总", "每文件事件数/有效率/异常计数（summary.xlsx）"),
)}


def resolve_mods(ids) -> tuple[str, ...]:
    """Expand prerequisites, drop unknown ids, dedupe, order by :data:`ORDER`."""
    if not ids:
        return ()
    wanted: set[str] = set()
    unknown: set[str] = set()
    stack = list(ids)
    while stack:
        mid = stack.pop()
        if mid in wanted or mid in unknown:
            continue
        spec = MODS.get(mid)
        if spec is None:
            unknown.add(mid)
            continue
        wanted.add(mid)
        stack.extend(spec.requires)
    if unknown:
        warnings.warn(f"unknown mod id(s) ignored: {sorted(unknown)}", stacklevel=2)
    return tuple(m for m in ORDER if m in wanted)


def all_mods() -> tuple[str, ...]:
    """Every known mod id, in dependency order."""
    return ORDER
