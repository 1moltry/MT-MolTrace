"""Stable contracts for the event-description (fingerprint) layer.

This module is Qt-free and ABF-free. It defines:

* **event identity** — ``source_id`` (recording content) and ``event_key``
  (one physical event boundary), both stable across re-runs and independent of
  table row numbers;
* **:class:`EventView`** — the only input a describer may consume: the analysis
  trace *and* the raw trace for the same context window, global sample
  coordinates, open-pore / blockade references and the analysis provenance;
* **:class:`Segment` / :class:`EventDescription`** — the output contract, with
  relative and global sample coordinates;
* **:class:`RunManifest`** — the run-level provenance written next to a
  fingerprint export;
* hashing helpers for parameter and data digests (the description cache key).

Backward compatibility: every key of the 1.0 JSON payload is still emitted;
new keys are appended and ``schema_version`` becomes ``1.1``.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import numpy as np

#: Current fingerprint JSON schema version.
SCHEMA_VERSION = "1.1"

#: Effective bandwidth measured on the old projects' PSD; a hint only.
EFFECTIVE_BW_HZ = 1200.0


# --------------------------------------------------------------------------- #
# Event identity
# --------------------------------------------------------------------------- #

def source_id_for_path(path: str | Path) -> str:
    """``source_id`` of an ABF file: SHA-256 of its content.

    Returns ``"sha256:<hex>"``. A missing or unreadable file falls back to
    ``"fallback:<hex>"`` built from path + size + mtime (see
    :func:`fallback_source_id`).
    """
    p = Path(path)
    h = hashlib.sha256()
    try:
        with p.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
    except OSError:
        return fallback_source_id(p)
    return "sha256:" + h.hexdigest()


def fallback_source_id(path: str | Path, current: np.ndarray | None = None,
                       mtime: float | None = None) -> str:
    """Degraded identity from path + size + mtime.

    When the file cannot be stat'ed (synthetic in-memory recordings), the
    in-memory trace digest is mixed in as well, so two synthetic recordings of
    the same length do not collide.
    """
    p = Path(path)
    try:
        st = p.stat()
        size, mtime = int(st.st_size), float(st.st_mtime)
    except OSError:
        size, mtime = 0, float(mtime or 0.0)
    parts = [str(p), str(size), f"{mtime:.6f}"]
    if size == 0 and current is not None:
        parts.append(_array_digest(current))
    return "fallback:" + hashlib.sha1("|".join(parts).encode()).hexdigest()


def source_id_for_rec(rec, *, refresh: bool = False) -> str:
    """``source_id`` for an :class:`nanopore.io.AbfRecording`, computed once."""
    cached = getattr(rec, "_mol_source_id", None)
    if cached and not refresh:
        return cached
    path = getattr(rec, "path", "")
    sid = source_id_for_path(path) if path else fallback_source_id(
        "", getattr(rec, "current", None))
    try:
        setattr(rec, "_mol_source_id", sid)
    except Exception:  # noqa: BLE001 — a frozen/slots record is still usable
        pass
    return sid


def event_key(source_id: str, fs_hz: float, start_sample: int,
              end_sample: int) -> str:
    """Stable key of one physical event boundary.

    Deliberately excludes the detector id, the event row number and any
    anomaly/threshold setting: the same physical boundary described by a
    different detector or after changing ``min_toff`` keeps the same key.
    """
    payload = (f"{source_id}|{float(fs_hz):.6f}|"
               f"{int(start_sample)}|{int(end_sample)}")
    return hashlib.sha1(payload.encode()).hexdigest()[:16]


def _array_digest(x: np.ndarray) -> str:
    a = np.ascontiguousarray(np.asarray(x, dtype=np.float64))
    return hashlib.sha1(a.tobytes()).hexdigest()


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, float) and not np.isfinite(value):
        return str(value)
    return value


def params_hash(params: dict[str, Any] | None) -> str:
    """Digest of the resolved describer parameters (12 hex chars)."""
    blob = json.dumps(_jsonable(params or {}), sort_keys=True,
                      ensure_ascii=False, default=str)
    return hashlib.sha1(blob.encode()).hexdigest()[:12]


def data_hash(view: "EventView") -> str:
    """Digest of the exact data a description was computed from.

    Covers the context window actually handed to the describer, the event
    boundary, which trace was used, and the three reference values
    (``i_open`` / ``i_blockade`` / ``sigma_open``).
    """
    h = hashlib.sha1()
    h.update(np.ascontiguousarray(view.current, dtype=np.float64).tobytes())
    h.update(f"|{view.start}|{view.end}|{view.trace_source}".encode())
    h.update(np.asarray([view.i_open, view.i_blockade, view.sigma_open],
                        dtype=np.float64).tobytes())
    return h.hexdigest()[:12]


# --------------------------------------------------------------------------- #
# EventView
# --------------------------------------------------------------------------- #

@dataclass
class EventView:
    """Read-only view of one event plus its context window.

    ``analysis`` is the trace the detector actually saw (low-passed when the
    low-pass mod is on); ``raw`` is the same window of the original recording.
    ``current`` selects one of them according to ``trace_source``, which comes
    from the describer's ``input_trace`` declaration.
    """

    event_id: int
    source: str
    fs: float
    start: int                  # event start, global samples (inclusive)
    end: int                    # event end, global samples (exclusive)
    ctx_start: int              # context window start, global samples
    ctx_end: int                # context window end, global samples
    analysis: np.ndarray        # context-window analysis trace (pA)
    raw: np.ndarray | None = None   # context-window raw trace (pA)
    trace_source: str = "analysis"  # "analysis" | "raw"
    i_open: float = float("nan")       # open-pore current (pA)
    i_blockade: float = float("nan")   # blockade baseline inside the body (pA)
    sigma_open: float = float("nan")   # open-pore noise sigma (pA)
    i_open_source: str = ""
    i_blockade_source: str = ""
    sigma_source: str = ""
    lowpass_hz: float | None = None
    effective_bw_hz: float | None = EFFECTIVE_BW_HZ
    voltage: np.ndarray | None = None      # context-window protocol voltage (mV)
    i0_profile: np.ndarray | None = None   # context-window dynamic I0 (pA)
    direction: int = 0                     # -1 down, +1 up, 0 unknown
    state: str = "A"
    source_id: str = ""
    event_key: str = ""
    legacy_event_id: int | None = None
    detector_id: str = ""
    detector_version: str = ""
    detector_params: dict[str, Any] = field(default_factory=dict)
    analysis_params: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    # --- trace selection -------------------------------------------------- #

    @property
    def current(self) -> np.ndarray:
        """The trace the describer consumes (analysis by default)."""
        if self.trace_source == "raw" and self.raw is not None:
            return self.raw
        return self.analysis

    @property
    def fs_hz(self) -> float:
        return self.fs

    def _rel(self, a: int, b: int) -> slice:
        return slice(max(0, a - self.ctx_start), min(len(self.current), b - self.ctx_start))

    # --- body views ------------------------------------------------------- #

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
        return (np.arange(len(self.current)) + self.ctx_start - self.start) / self.fs

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

    @property
    def global_span(self) -> tuple[int, int]:
        return int(self.start), int(self.end)


# --------------------------------------------------------------------------- #
# Segment / EventDescription
# --------------------------------------------------------------------------- #

@dataclass
class Segment:
    """One sub-structure inside an event (a step, shape or fingerprint).

    ``start`` / ``end`` are sample offsets from the event start (half-open),
    which keeps them stable when the context window changes. ``start_global`` /
    ``end_global`` are filled by the engine so every consumer can connect a
    segment back to the recording without knowing the event row.
    """

    start: int
    end: int
    level_pA: float | None = None
    level_rel: float | None = None      # level_pA - i_blockade
    level_norm: float | None = None     # level_pA / i_open
    attrs: dict[str, Any] = field(default_factory=dict)
    start_global: int | None = None
    end_global: int | None = None

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
    schema_version: str = SCHEMA_VERSION
    # --- 1.1 additions ---
    event_key: str = ""
    source_id: str = ""
    fs_hz: float = 0.0
    event_start: int | None = None
    event_end: int | None = None
    legacy_event_id: int | None = None
    params_hash: str = ""
    trace_source: str = ""
    coverage: dict[str, Any] = field(default_factory=dict)
    attrs: dict[str, Any] = field(default_factory=dict)
    detector_id: str = ""
    analysis_params: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunManifest:
    """Run-level provenance written next to a fingerprint export."""

    source_id: str = ""
    source_name: str = ""
    fs_hz: float = 0.0
    detector_id: str = ""
    detector_version: str = ""
    detector_params: dict[str, Any] = field(default_factory=dict)
    analysis_params: dict[str, Any] = field(default_factory=dict)
    describer: str = ""
    describer_version: str = ""
    params_hash: str = ""
    trace_source: str = "analysis"
    schema_version: str = SCHEMA_VERSION

    def to_json(self) -> dict:
        return _jsonable({
            "source_id": self.source_id,
            "source_name": self.source_name,
            "fs_hz": self.fs_hz,
            "detector_id": self.detector_id,
            "detector_version": self.detector_version,
            "detector_params": self.detector_params,
            "analysis_params": self.analysis_params,
            "describer": self.describer,
            "describer_version": self.describer_version,
            "params_hash": self.params_hash,
            "trace_source": self.trace_source,
            "schema_version": self.schema_version,
        })


# --------------------------------------------------------------------------- #
# Serialization (old keys preserved, new keys appended)
# --------------------------------------------------------------------------- #

def to_json(desc: EventDescription) -> dict:
    """Full nested structure; payload keeps arbitrary nesting."""
    return _jsonable({
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
             "level_rel": s.level_rel, "level_norm": s.level_norm,
             "attrs": s.attrs,
             "start_global": s.start_global, "end_global": s.end_global}
            for s in desc.segments
        ],
        # 1.1 additions
        "event_key": desc.event_key,
        "source_id": desc.source_id,
        "fs_hz": desc.fs_hz,
        "event_start": desc.event_start,
        "event_end": desc.event_end,
        "legacy_event_id": desc.legacy_event_id,
        "params_hash": desc.params_hash,
        "trace_source": desc.trace_source,
        "coverage": desc.coverage,
        "attrs": desc.attrs,
        "detector_id": desc.detector_id,
        "analysis_params": desc.analysis_params,
    })


def manifest_for(descs: Iterable[EventDescription], source: str = "",
                 *, source_id: str = "", fs_hz: float | None = None) -> RunManifest:
    descs = list(descs)
    first = descs[0] if descs else None
    if first is None:
        return RunManifest(source_id=source_id, source_name=source,
                           fs_hz=fs_hz or 0.0)
    return RunManifest(
        source_id=first.source_id,
        source_name=source or first.source,
        fs_hz=first.fs_hz,
        detector_id=first.detector_id,
        detector_version=first.attrs.get("detector_version", ""),
        detector_params=first.attrs.get("detector_params", {}),
        analysis_params=first.analysis_params,
        describer=first.describer,
        describer_version=first.describer_version,
        params_hash=first.params_hash,
        trace_source=first.trace_source,
    )


def descriptions_to_json(descs: Iterable[EventDescription], source: str,
                         *, source_id: str = "", fs_hz: float | None = None) -> dict:
    descs = list(descs)
    first = descs[0] if descs else None
    sid = first.source_id if first else source_id
    rate = first.fs_hz if first else (fs_hz or 0.0)
    return {
        "schema_version": SCHEMA_VERSION,
        "source": source,
        "describer": first.describer if first else "",
        "describer_version": first.describer_version if first else "",
        "params": first.params if first else {},
        "events": [to_json(d) for d in descs],
        # 1.1 additions
        "source_id": sid,
        "fs_hz": rate,
        "params_hash": first.params_hash if first else "",
        "trace_source": first.trace_source if first else "",
        "manifest": manifest_for(descs, source, source_id=source_id,
                                 fs_hz=fs_hz).to_json(),
    }


def dumps(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=1, default=float)
