"""Description engine: resolve a describer, build its view, finalize the output.

The engine owns the pieces every describer would otherwise duplicate:

* resolved parameters (defaults + overrides, unknown keys dropped);
* the cache key ``(event_key, describer, version, params_hash, data_hash)``;
* filling the 1.1 contract fields (source id, global segment coordinates,
  coverage, parameter digest) so a describer only has to emit segments.
"""
from __future__ import annotations

from typing import Any, Mapping

from .contracts import EventDescription, data_hash, params_hash
from .context import build_event_view
from .registry import DescriberUnavailable, EventDescriber, get_describer


def _unavailable(describer: EventDescriber, view, params: dict,
                 exc: Exception) -> EventDescription:
    """A safe description for a describer that cannot run (model/dep missing)."""
    return EventDescription(
        event_id=getattr(view, "event_id", 0),
        source=getattr(view, "source", ""),
        describer=describer.id,
        describer_version=describer.version,
        params=dict(params or {}),
        quality={"valid": False, "reason": str(exc)},
    )


def resolve_params(describer: EventDescriber,
                   overrides: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return describer.resolve_params(overrides)


def finalize_description(desc: EventDescription, view,
                         describer: EventDescriber,
                         params: Mapping[str, Any] | None = None
                         ) -> EventDescription:
    """Fill the 1.1 contract fields on a description built outside the engine.

    The research decoders call ``describer.decode(...)`` directly (they already
    hold a fitted model); this wrapper keeps their output traceable exactly like
    the normal ``describe_event`` path.
    """
    return _finalize(desc, view, describer, resolve_params(describer, params))


def view_for(result, index: int, describer: EventDescriber, *,
             input_trace: str | None = None):
    return build_event_view(result, index,
                            input_trace=input_trace or describer.input_trace)


def cache_key(view, describer: EventDescriber,
              params: Mapping[str, Any] | None = None) -> tuple:
    """Cache identity: same event, describer, version, parameters and data."""
    resolved = resolve_params(describer, params)
    return (view.event_key, describer.id, describer.version,
            params_hash(resolved), data_hash(view))


def cache_key_for(result, index: int, describer: EventDescriber, *,
                  params: Mapping[str, Any] | None = None,
                  input_trace: str | None = None) -> tuple:
    view = view_for(result, index, describer, input_trace=input_trace)
    return cache_key(view, describer, params)


def _finalize(desc: EventDescription, view, describer: EventDescriber,
              params: dict[str, Any]) -> EventDescription:
    desc.schema_version = "1.1"
    desc.source = view.source
    desc.event_key = view.event_key
    desc.source_id = view.source_id
    desc.fs_hz = view.fs
    desc.event_start = view.start
    desc.event_end = view.end
    desc.legacy_event_id = view.legacy_event_id
    desc.params_hash = params_hash(params)
    desc.trace_source = view.trace_source
    desc.detector_id = view.detector_id
    desc.analysis_params = dict(view.analysis_params)

    for seg in desc.segments:
        if seg.start_global is None:
            seg.start_global = view.start + int(seg.start)
        if seg.end_global is None:
            seg.end_global = view.start + int(seg.end)

    covered = sum(seg.width_samples for seg in desc.segments)
    if not desc.segments:
        # a scalar description covers the whole body; an invalid one covers none
        covered = view.n_samples if desc.quality.get("valid", True) else 0
    n = max(view.n_samples, 1)
    desc.coverage = {
        "event_samples": int(view.n_samples),
        "covered_samples": int(covered),
        "coverage_frac": float(covered) / n,
        "trimmed_samples": int(max(0, view.n_samples - covered)),
    }
    desc.attrs = dict(desc.attrs or {})
    desc.attrs.setdefault("detector_version", view.detector_version)
    desc.attrs.setdefault("detector_params", dict(view.detector_params))
    desc.attrs.setdefault("i_open_source", view.i_open_source)
    desc.attrs.setdefault("i_blockade_source", view.i_blockade_source)
    desc.attrs.setdefault("sigma_source", view.sigma_source)
    desc.attrs.setdefault("direction", view.direction)
    if not desc.quality:
        desc.quality = {"valid": True}
    return desc


def describe_event(result, index: int, describer: EventDescriber, *,
                   params: Mapping[str, Any] | None = None,
                   input_trace: str | None = None) -> EventDescription:
    """Describe one kept event of an ``AnalysisResult``."""
    resolved = resolve_params(describer, params)
    view = view_for(result, index, describer, input_trace=input_trace)
    try:
        desc = describer.describe(view, resolved)
    except DescriberUnavailable as exc:
        desc = _unavailable(describer, view, resolved, exc)
    return _finalize(desc, view, describer, resolved)


def describe_result(result, cfg=None, *, describer_id: str | None = None,
                    params: Mapping[str, Any] | None = None,
                    progress=None, cancel=None) -> list[EventDescription]:
    """Describe every kept event of an ``AnalysisResult``.

    ``cfg`` (a ``PipelineConfig``) supplies the describer id and parameter
    overrides; when omitted the result's own stored config is used.
    ``progress(done, total)`` and ``cancel()`` let a batch/GUI export report
    progress and stop between events.
    """
    cfg = cfg if cfg is not None else getattr(result, "config", None)
    desc_id = describer_id or (getattr(cfg, "describer", "") if cfg else "") or "dp_bic"
    overrides = params if params is not None else (
        getattr(cfg, "describe_params", {}) if cfg else {})
    describer = get_describer(desc_id)
    resolved = resolve_params(describer, overrides)

    total = len(result.df)
    out: list[EventDescription] = []
    for i in range(total):
        if cancel is not None and cancel():
            raise RuntimeError("已取消")
        view = view_for(result, i, describer)
        try:
            desc = describer.describe(view, resolved)
        except DescriberUnavailable as exc:
            desc = _unavailable(describer, view, resolved, exc)
        out.append(_finalize(desc, view, describer, resolved))
        if progress is not None:
            progress(i + 1, total)
    return out


def describe_rows_compat(df, rec, cfg) -> list[EventDescription]:
    """Compatibility path for a recording + feature table (raw trace only)."""
    from .context import view_from_row

    desc_id = getattr(cfg, "describer", "") or "dp_bic"
    describer = get_describer(desc_id)
    resolved = resolve_params(describer, getattr(cfg, "describe_params", {}))
    out: list[EventDescription] = []
    for i, (_, row) in enumerate(df.iterrows(), start=1):
        view = view_from_row(rec, row, event_id=i)
        try:
            desc = describer.describe(view, resolved)
        except DescriberUnavailable as exc:
            desc = _unavailable(describer, view, resolved, exc)
        out.append(_finalize(desc, view, describer, resolved))
    return out
