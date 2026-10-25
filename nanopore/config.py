"""Pipeline parameters, savable/loadable as JSON (a reusable analysis protocol)."""

from __future__ import annotations

import json
import warnings
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path


@dataclass
class PipelineConfig:
    # --- preprocessing ---
    filter_lowpass_hz: float | None = None  # None = no extra digital filtering

    # --- baseline / level estimation (replaces manual marker dragging) ---
    level0: float | None = None  # manual override of baseline (pA)
    level1: float | None = None  # manual override of event level (pA, signed offset from baseline applied at runtime)
    hist_bins: int = 200         # all-points amplitude histogram bins for level estimation
    polarity: int | None = None  # event search direction: None = auto from the level
                                 # histogram; 1 = upward only; -1 = downward only;
                                 # 0 = both (multi-level peptides whose blockades fall on
                                 # either side of the open pore, e.g. ARNKRS). The
                                 # detector already walks a +/-8 step level grid, so 0
                                 # also enables multi-level detection within each side.

    # --- event detection (level/threshold single-channel search) ---
    ignore_duration_ms: float = 2.0    # Ignore duration (from baseline): out-of-level
                                       # time below this is spike-rejected, not registered
    ignore_event_duration_ms: float = 50.0  # Ignore duration (from event levels): deviations
                                            # out of an event level (incl. brief returns to
                                            # baseline) shorter than this continue the event
                                            # (event-level ignore duration)
    level_contribution: float = 0.10   # exponential update weight for level tracking (10%)
    update_levels: str = "baseline"    # "baseline" (keep deltas) or "all" (independent)
    dwell_min_frac: float = 0.30       # min fraction of trimmed body near a level step to keep an event
    event_plateau_min_frac: float = 0.0  # stability gate: min fraction of the event body dwelling on
                                         # ONE level (nearest integer level, +/-0.5 step). Below this
                                         # the event oscillates across levels (flicker/glitch) and is
                                         # rejected. 0 = disabled (a fast flicker passes the plain
                                         # dwell/spike checks; raising this removes it, but also
                                         # removes genuine multi-level events -> per-file knob).
    min_toff_ms: float = 10.0          # export filter: keep events with toff > this (ms)

    # --- feature modules (multi-select; the base pipeline always runs) ---
    # Optional stages/outputs to enable (see nanopore.mods). Empty = base only:
    # read -> level estimation -> detection -> features -> events table.
    # Detection *variants* (polarity / event_mode / plateau gate) stay plain
    # params below, not mods.
    enabled_mods: tuple[str, ...] = ()

    # --- event description / fingerprint (mod "describe") ---
    describer: str = "dp_bic"          # "dp_bic" (segments) or "scalar"
    describe_params: dict[str, float] = field(default_factory=dict)
                                       # overrides for the describer's ParamSpec defaults

    # --- detection variants (not mods; they change how the base detector works) ---
    event_mode: str = "level"          # "level" = threshold/level runs (default);
                                       # "burst" = dwell-envelope debounce (merges
                                       # glitches and open-pore hopping into one event)
    burst_enter_frac: float = 0.30     # burst: |I-I0| > this*step enters a blockade
    burst_exit_frac: float = 0.20      # burst: amplitude read from samples beyond this*step
    burst_min_gap_ms: float = 30.0     # burst: returns to open shorter than this do NOT split
    burst_min_block_ms: float = 2.0    # burst: blocked fragments shorter than this are dropped
    burst_open_cover: float = 0.75     # burst: a gap only splits when at least this fraction
                                       # of it lies within +/-enter_frac*step of the open
                                       # level; otherwise adjacent events merge
    burst_merge_max_ms: float = 200.0  # burst: only merge non-open gaps up to this long
                                       # (longer shallow states stay separate events)
    burst_cross_baseline: bool = False  # burst: departures on EITHER side of I0 count as
                                       # one event (multi-level / baseline-crossing signals)
    burst_min_occupied_frac: float = 0.30  # burst: reject an event whose body is actually
                                           # blocked for less than this fraction of its dwell
                                           # (a chain of sparse spikes is not an event)
    burst_min_depth_frac: float = 0.15     # burst: ... unless its body median is deflected by
                                           # at least this * step (keeps shallow sustained states)

    # --- event detector selection ---
    # "" = legacy: derived from event_mode (level/burst); explicit values let the
    # GUI/CLI choose one detector from the shared registry.
    detector: str = ""

    # --- plateau detector (detector="plateau"; ported from npsweep) ---
    plateau_direction: str = "auto"        # auto (from polarity) / down / up / both
    plateau_enter_depth_pA: float = 60.0   # a run must reach this depth to be an event
    plateau_exit_depth_pA: float = 15.0    # boundary sits here (close to open pore)
    plateau_min_open_ms: float = 1.0       # returns shorter than this do not split an event
    plateau_min_dwell_ms: float = 0.0      # detector-side dwell floor (0 = leave to min_toff)
    plateau_dwell_max_ms: float = 1e12
    plateau_depth_min_pA: float = 0.0
    plateau_depth_max_pA: float = 1e12
    plateau_exclude_voltage: bool = True   # mask protocol-voltage segments
    plateau_voltage_tol_mv: float = 20.0
    plateau_exclude_pulse_cleared: bool = True  # drop events ended by a voltage pulse
    plateau_pulse_tol_ms: float = 50.0
    plateau_exclude_rupture: bool = True   # drop membrane-rupture / pore-collapse events
    plateau_artifact_abs_pA: float = 1000.0  # mask |I| above this (0 = off)
    plateau_artifact_diff_pA: float = 500.0  # mask |dI| above this (0 = off)
    plateau_cutoff_hz: float | None = None   # filter cutoff for edge trimming

    # --- anomaly detection (mod "anomaly") ---
    jump_min_ms: float = 50.0          # macro: sustained shift must persist at least this long
    noise_sigma_mult: float = 4.0      # macro: sliding noise std above this multiple of robust sigma marks jitter
    jitter_min_ms: float = 100.0
    # fine-grained artifact detector: reverse voltage / rupture / graded jitter /
    # irregular blockage with spontaneous-vs-manual recovery; needs the voltage
    # trace and the dynamic I0 baseline (mod "refined_anomaly")
    refined_jitter_window_ms: float = 100.0
    refined_jitter_mild_ratio: float = 3.0
    refined_jitter_severe_ratio: float = 8.0
    refined_jitter_osc_floor: float = 0.45
    refined_blockage_min_ms: float = 500.0
    refined_blockage_fraction: float = 0.45
    refined_rupture_iqr_min_pA: float = 80.0
    refined_rupture_noise_min_ratio: float = 2.0
    refined_rupture_level_frac_max: float = 0.28   # rupture window must have <= this fraction of
                                                   # samples near a significant level (dense event
                                                   # clusters are level-structured -> not rupture)
    refined_jitter_level_frac_max: float = 0.20    # macro jitter block must have <= this fraction of
                                                   # samples near a non-baseline level
    # slow baseline drift / instability (refined detector): a gradual,
    # irreversible displacement of the open-pore level that is ALSO accompanied
    # by high signal spread. Both keys required (see anomaly.ArtifactConfig).
    refined_drift_enabled: bool = True
    refined_drift_block_s: float = 15.0
    refined_drift_min_s: float = 20.0
    refined_drift_min_frac: float = 0.05
    refined_drift_iqr_ratio: float = 3.0
    refined_drift_step_pA: float = 6.0
    refined_drift_rupture_ratio: float = 4.0

    # --- features ---
    pre_event_ms: float = 25.0         # open-pore current window before the event
    dr_pA: float = 5.0                 # |Io(i)-I0|>5 pA fallback threshold for Io continuity

    # --- output ---
    label: str = ""                    # Label column value; defaults to file stem

    def __post_init__(self) -> None:
        # JSON has no tuples: canonicalize collection fields on every path so
        # save -> load preserves equality and callers can compare configurations.
        self.enabled_mods = tuple(self.enabled_mods or ())
        self.describe_params = dict(self.describe_params or {})

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def from_dict(cls, data: dict) -> "PipelineConfig":
        valid = {f.name for f in fields(cls)}
        unknown = sorted(set(data) - valid)
        if unknown:
            warnings.warn(
                "ignoring unknown config key(s): " + ", ".join(unknown),
                UserWarning, stacklevel=2)
        return cls(**{k: v for k, v in data.items() if k in valid})

    @classmethod
    def load(cls, path: str | Path) -> "PipelineConfig":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)
