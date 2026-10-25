"""Shared analysis orchestration: base pipeline + the enabled feature modules.

Both the batch pipeline (:func:`nanopore.pipeline.process_file`) and the GUI
worker (:class:`nanopore.gui.controller.AnalysisWorker`) call :func:`analyze`,
so the two paths can never drift apart.

Base pipeline (always):
    read -> estimate levels -> detect events -> extract features -> exclusions

Each enabled mod (see :mod:`nanopore.mods`) adds its stage:
    lowpass          -> filter the trace before detection
    dynamic_i0       -> per-event open-pore Io from a dynamic baseline
    anomaly          -> macro anomaly regions + event exclusion
    refined_anomaly  -> graded anomaly kinds (needs anomaly + dynamic_i0)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .anomaly import (AnomalyResult, detect_anomalies, detect_artifact_segments,
                      merge_anomaly_results)
from .baseline import Levels, estimate_levels, set_polarity
from .config import PipelineConfig
from .detect import DetectionResult, detect, resolve_detector_id
from .features import classify_exclusions, compute_features
from .mods import resolve_mods
from .registry import normalize_config


@dataclass
class AnalysisResult:
    rec: object                    # io.AbfRecording
    lv: Levels
    filtered: np.ndarray           # trace actually fed to the detector
    det: DetectionResult
    i0_profile: object | None      # baseline_i0.I0Profile or None
    anom: AnomalyResult | None
    df: pd.DataFrame               # kept events (feature table)
    df_excluded: pd.DataFrame | None
    descs: list | None = None      # per-kept-event EventDescription (mod "describe")
    detector_id: str = ""
    detector_rejected: int = 0
    enabled_mods: tuple[str, ...] = ()
    anomaly_enabled: bool = False
    i0_used: bool = False
    i0_source: str = ""


def analyze(rec, cfg: PipelineConfig, *, with_descriptions: bool = True) -> AnalysisResult:
    """Run the base pipeline plus ``cfg.enabled_mods`` on an already-read record.

    ``with_descriptions=False`` skips the (potentially slow) per-event describe
    stage; the GUI computes descriptions lazily for the selected event instead.
    """
    cfg = normalize_config(cfg)
    mods = set(resolve_mods(cfg.enabled_mods))

    lv = estimate_levels(
        rec.current,
        hist_bins=cfg.hist_bins,
        baseline=cfg.level0,
        event_level=cfg.level1,
    )
    if cfg.polarity is not None:
        set_polarity(lv, cfg.polarity)   # manual search-direction override

    filtered = rec.current
    cutoff = cfg.filter_lowpass_hz if "lowpass" in mods else None
    if cutoff:
        from .preprocess import lowpass

        filtered = lowpass(rec.current, rec.sample_rate_hz, cutoff)

    # burst mode needs a per-sample open-pore reference so pore-state switches
    # are not read as blockades; features consume this profile only when the
    # dynamic_i0 mod is enabled
    need_i0 = ("dynamic_i0" in mods) or (resolve_detector_id(cfg) == "burst")
    i0_for_detect = None
    if need_i0:
        from .baseline_i0 import build_dynamic_baseline

        i0_for_detect = build_dynamic_baseline(rec.current, rec.sample_rate_hz,
                                               anchor_level=lv.level0)

    det = detect(filtered, rec.sample_rate_hz, lv, cfg,
                 cutoff_hz=cutoff, i0_profile=i0_for_detect,
                 voltage=rec.protocol_voltage)

    i0_profile = i0_for_detect if "dynamic_i0" in mods else None

    anom = None
    if "anomaly" in mods:
        macro = detect_anomalies(
            rec.current,
            rec.sample_rate_hz,
            open_pore=lv.level0,
            noise_sigma=lv.noise_sigma,
            event_levels=lv.levels,
            jump_min_ms=cfg.jump_min_ms,
            jitter_mult=cfg.noise_sigma_mult,
            jitter_min_ms=cfg.jitter_min_ms,
            jitter_level_frac_max=cfg.refined_jitter_level_frac_max,
        )
        refined = None
        if "refined_anomaly" in mods:
            acfg = _artifact_config(cfg)
            refined = detect_artifact_segments(
                rec.current,
                rec.sample_rate_hz,
                voltage=rec.protocol_voltage,
                i0_profile=i0_profile,
                open_pore=lv.level0,
                event_levels=lv.levels,
                cfg=acfg,
            )
        anom = merge_anomaly_results(macro, refined)

    df = compute_features(
        det,
        filtered,
        rec.sample_rate_hz,
        label=cfg.label or rec.path.stem,
        pre_event_ms=cfg.pre_event_ms,
        dr_pA=cfg.dr_pA,
        i0_profile=i0_profile,
    )
    df, df_excluded = classify_exclusions(df, anom.regions if anom else [], cfg.min_toff_ms)

    # Detector-owned validity rejections are not anomaly regions. Give them the
    # same feature columns and a distinct drop stage/code so the UI and exports
    # can trace them without mixing them into the optional anomaly counts.
    if det.rejected:
        rejected_events = [r.event for r in det.rejected]
        rejected_res = DetectionResult(
            events=rejected_events,
            levels_initial=det.levels_initial,
            sample_rate_hz=det.sample_rate_hz,
            level0_final=det.level0_final,
            level0_refs=np.array([e.level0_ref_pA for e in rejected_events],
                                 dtype=float),
        )
        rejected_df = compute_features(
            rejected_res,
            filtered,
            rec.sample_rate_hz,
            label=cfg.label or rec.path.stem,
            pre_event_ms=cfg.pre_event_ms,
            dr_pA=cfg.dr_pA,
            i0_profile=i0_profile,
        )
        rejected_df["drop_reason"] = [r.code for r in det.rejected]
        rejected_df["drop_code"] = [r.code for r in det.rejected]
        rejected_df["drop_stage"] = [r.stage for r in det.rejected]
        if df_excluded is None or len(df_excluded) == 0:
            df_excluded = rejected_df.reset_index(drop=True)
        else:
            df_excluded = pd.concat([df_excluded, rejected_df], ignore_index=True)

    descs = None
    if with_descriptions and "describe" in mods:
        from .describe import describe_rows

        descs = describe_rows(df, rec, cfg)

    detector_id = resolve_detector_id(cfg)
    anomaly_enabled = "anomaly" in mods
    i0_used = bool(detector_id == "burst" and i0_for_detect is not None)
    return AnalysisResult(
        rec, lv, filtered, det, i0_profile, anom, df, df_excluded, descs,
        detector_id=detector_id,
        detector_rejected=len(det.rejected),
        enabled_mods=tuple(sorted(mods)),
        anomaly_enabled=anomaly_enabled,
        i0_used=i0_used,
        i0_source="detector:burst" if i0_used else "",
    )


def _artifact_config(cfg: PipelineConfig):
    from .anomaly import ArtifactConfig

    return ArtifactConfig(
        jitter_window_ms=cfg.refined_jitter_window_ms,
        jitter_mild_ratio=cfg.refined_jitter_mild_ratio,
        jitter_severe_ratio=cfg.refined_jitter_severe_ratio,
        jitter_osc_floor=cfg.refined_jitter_osc_floor,
        blockage_min_ms=cfg.refined_blockage_min_ms,
        blockage_fraction=cfg.refined_blockage_fraction,
        rupture_iqr_min_pA=cfg.refined_rupture_iqr_min_pA,
        rupture_noise_min_ratio=cfg.refined_rupture_noise_min_ratio,
        rupture_level_frac_max=cfg.refined_rupture_level_frac_max,
        drift_enabled=cfg.refined_drift_enabled,
        drift_block_s=cfg.refined_drift_block_s,
        drift_min_s=cfg.refined_drift_min_s,
        drift_min_frac=cfg.refined_drift_min_frac,
        drift_iqr_ratio=cfg.refined_drift_iqr_ratio,
        drift_step_pA=cfg.refined_drift_step_pA,
        drift_rupture_ratio=cfg.refined_drift_rupture_ratio,
    )
