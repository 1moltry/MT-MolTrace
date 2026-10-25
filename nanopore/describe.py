"""Compatibility facade for the event-description layer.

The implementation now lives in :mod:`nanopore.fingerprint`:

* ``contracts`` — event identity, :class:`EventView`, :class:`Segment`,
  :class:`EventDescription`, :class:`RunManifest`, serialization;
* ``context`` — building a view from an ``AnalysisResult``;
* ``registry`` — describer registration and maturity;
* ``engine`` — parameter resolution, cache keys, finalization.

This module keeps the old import paths and signatures working:

* ``make_event_view(rec, row, event_id=...)`` — legacy recording + row form;
  the new production form is ``make_event_view(analysis_result, index)``;
* ``describe_rows(df, rec, cfg)`` — legacy form, which has no analysis trace
  and therefore describes the raw trace;
* ``to_json`` / ``descriptions_to_json`` / ``dumps``.

New code should import from :mod:`nanopore.fingerprint` directly.
"""
from __future__ import annotations

from typing import Mapping

import numpy as np

from .fingerprint import (EFFECTIVE_BW_HZ, SCHEMA_VERSION, EventDescription,
                          EventDescriber, EventView, IntervalEval, RunManifest,
                          Segment, build_event_view, data_hash, describe_event,
                          describe_meta, describe_result, describe_rows_compat,
                          describer_ids, descriptions_to_json, dumps,
                          estimate_blockade_baseline, estimate_i_open,
                          estimate_sigma_open, evaluate_intervals, event_key,
                          get_describer, interval_f1, list_describers,
                          match_intervals, params_hash, register,
                          resolve_params, source_id_for_path,
                          source_id_for_rec, to_global_intervals,
                          to_global_intervals_by_event, to_json, view_from_row)
from .fingerprint.builtin import (ClassicDescriber, DPBICDescriber,
                                  ScalarDescriber)


def make_event_view(source, row: Mapping | int | None = None, *,
                    event_id: int = 1, **kwargs) -> EventView:
    """Build an :class:`EventView`.

    * ``make_event_view(result, index)`` — production form: an
      ``AnalysisResult`` plus a 0-based kept-event index. Uses the analysis
      trace, the dynamic I0 profile and the voltage trace.
    * ``make_event_view(rec, row, event_id=...)`` — legacy form: a recording
      plus a feature-table row. Raw trace only.
    """
    if hasattr(source, "df") and hasattr(source, "filtered"):
        if not isinstance(row, (int, np.integer)):
            raise TypeError("make_event_view(AnalysisResult, index) needs an int index")
        return build_event_view(source, int(row), **kwargs)
    if row is None:
        raise TypeError("make_event_view(rec, row) needs a feature-table row")
    return view_from_row(source, row, event_id=event_id, **kwargs)


def describe_rows(df, rec, cfg) -> list[EventDescription]:
    """Describe every row of ``df`` from a recording (raw trace only)."""
    return describe_rows_compat(df, rec, cfg)


__all__ = [
    "EFFECTIVE_BW_HZ", "SCHEMA_VERSION", "EventView", "Segment",
    "EventDescription", "RunManifest", "EventDescriber",
    "ScalarDescriber", "DPBICDescriber", "ClassicDescriber",
    "register", "get_describer", "list_describers", "describer_ids",
    "describe_meta", "resolve_params",
    "make_event_view", "build_event_view", "view_from_row", "describe_rows",
    "describe_event", "describe_result",
    "estimate_i_open", "estimate_sigma_open", "estimate_blockade_baseline",
    "source_id_for_path", "source_id_for_rec", "event_key",
    "params_hash", "data_hash",
    "to_global_intervals", "to_global_intervals_by_event",
    "match_intervals", "interval_f1", "evaluate_intervals", "IntervalEval",
    "to_json", "descriptions_to_json", "dumps",
]
