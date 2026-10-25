"""Single source of truth for event-detector metadata.

The numerical implementations stay in :mod:`nanopore.detect` and
:mod:`nanopore.detect_plateau`. This module only describes their public ids,
labels, parameter ownership and data requirements so the GUI, CLI, comparison
window and batch dialog cannot drift into separate lists.

Detection algorithms are deliberately *not* merged: level, burst and plateau
have different boundary semantics. They share a catalog contract, not one
numerical implementation.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, replace
from typing import Any


@dataclass(frozen=True)
class DetectorSpec:
    id: str
    label: str
    desc: str
    legacy_event_mode: str          # "level" or "burst" for old configs
    params: tuple[str, ...] = ()    # PipelineConfig fields owned by this detector
    uses_voltage: bool = False
    uses_i0: bool = False
    version: str = "1"              # detector implementation version (provenance)


DETECTOR_ORDER: tuple[str, ...] = ("level", "burst", "plateau")

DETECTORS: dict[str, DetectorSpec] = {spec.id: spec for spec in (
    DetectorSpec(
        "level", "电平法",
        "逐样本最近电平；事件边界在电平中点。适合常规、多电平与肽信号。",
        legacy_event_mode="level",
        params=("ignore_duration_ms", "ignore_event_duration_ms",
                "level_contribution", "update_levels", "dwell_min_frac",
                "event_plateau_min_frac", "pre_event_ms"),
    ),
    DetectorSpec(
        "burst", "驻留包络（burst）",
        "驻留包络去抖；把毛刺、越孔和上下跳跃合并。适合抖动、碎片化阻孔。",
        legacy_event_mode="burst",
        params=("burst_enter_frac", "burst_exit_frac", "burst_min_gap_ms",
                "burst_min_block_ms", "burst_open_cover", "burst_merge_max_ms",
                "burst_cross_baseline", "burst_min_occupied_frac",
                "burst_min_depth_frac", "pre_event_ms"),
        uses_i0=True,
    ),
    DetectorSpec(
        "plateau", "平台滞回",
        "边界贴近开孔；部分恢复不切碎事件。适合糖与长阻孔信号。",
        legacy_event_mode="level",
        params=("plateau_direction", "plateau_enter_depth_pA",
                "plateau_exit_depth_pA", "plateau_min_open_ms",
                "plateau_min_dwell_ms", "plateau_dwell_max_ms",
                "plateau_depth_min_pA", "plateau_depth_max_pA",
                "plateau_exclude_voltage", "plateau_voltage_tol_mv",
                "plateau_exclude_pulse_cleared", "plateau_pulse_tol_ms",
                "plateau_exclude_rupture", "plateau_artifact_abs_pA",
                "plateau_artifact_diff_pA", "plateau_cutoff_hz"),
        uses_voltage=True,
    ),
)}


def list_detectors() -> list[DetectorSpec]:
    return [DETECTORS[k] for k in DETECTOR_ORDER]


def detector_ids() -> tuple[str, ...]:
    return DETECTOR_ORDER


def get_detector(detector_id: str) -> DetectorSpec:
    try:
        return DETECTORS[detector_id]
    except KeyError:
        raise KeyError(
            f"unknown detector {detector_id!r}; available: "
            + ", ".join(DETECTOR_ORDER)
        ) from None


def resolve_detector_id(cfg: Any, *, warn_unknown: bool = True) -> str:
    """Resolve an explicit detector id, falling back to the legacy event_mode."""
    explicit = str(getattr(cfg, "detector", "") or "")
    if explicit in DETECTORS:
        return explicit
    if explicit and warn_unknown:
        warnings.warn(
            f"unknown detector {explicit!r}; falling back to legacy event_mode",
            UserWarning, stacklevel=2)
    legacy = str(getattr(cfg, "event_mode", "level") or "level")
    return "burst" if legacy == "burst" else "level"


def normalize_config(cfg: Any, *, warn_unknown: bool = True) -> Any:
    """Return a copy with canonical detector/module fields.

    Unknown detector ids warn and fall back to the legacy field instead of
    silently rendering a different dropdown entry. Unknown module ids are
    already warned about by :func:`nanopore.mods.resolve_mods`.
    """
    from .mods import resolve_mods

    detector = resolve_detector_id(cfg, warn_unknown=warn_unknown)
    legacy_mode = "burst" if detector == "burst" else "level"

    # Describe ids are validated here as well, so a hand-edited config or an
    # old protocol cannot fail deep inside the description engine.
    from .fingerprint import describer_ids

    known_desc = set(describer_ids())
    describer = str(getattr(cfg, "describer", "") or "dp_bic")
    if describer not in known_desc:
        if warn_unknown:
            warnings.warn(
                f"unknown describer {describer!r}; falling back to dp_bic",
                UserWarning, stacklevel=2)
        describer = "dp_bic"
    extras = tuple(d for d in (getattr(cfg, "describers", ()) or ())
                   if d in known_desc and d != describer)

    return replace(
        cfg,
        detector=detector,
        event_mode=legacy_mode,
        enabled_mods=resolve_mods(tuple(getattr(cfg, "enabled_mods", ()) or ())),
        describer=describer,
        describers=extras,
    )
