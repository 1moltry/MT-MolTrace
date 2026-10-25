"""Unified event-fingerprint layer: contracts, context, registry, engine.

Importing this package registers the built-in describers (``scalar``,
``dp_bic``). Everything here is Qt-free and never reads an ABF directly.

The old :mod:`nanopore.describe` module remains as a compatibility facade that
re-exports this API.
"""
from __future__ import annotations

from .builtin import DPBICDescriber, ScalarDescriber  # explicit registration
from .context import (build_event_view, context_pad_samples,
                      estimate_blockade_baseline, estimate_i_open,
                      estimate_sigma_open, view_from_row)
from .contracts import (EFFECTIVE_BW_HZ, SCHEMA_VERSION, EventDescription,
                        EventView, RunManifest, Segment, data_hash,
                        descriptions_to_json, dumps, event_key,
                        fallback_source_id, manifest_for, params_hash,
                        source_id_for_path, source_id_for_rec, to_json)
from .engine import (cache_key, cache_key_for, describe_event, describe_result,
                     describe_rows_compat, resolve_params, view_for)
from .registry import (MATURITY_LEVELS, TRACE_SOURCES, EventDescriber,
                       describe_meta, describer_ids, get_describer,
                       list_describers, register)

__all__ = [
    "EFFECTIVE_BW_HZ", "SCHEMA_VERSION",
    "EventDescription", "EventView", "RunManifest", "Segment",
    "ScalarDescriber", "DPBICDescriber",
    "source_id_for_path", "fallback_source_id", "source_id_for_rec",
    "event_key", "params_hash", "data_hash",
    "to_json", "descriptions_to_json", "manifest_for", "dumps",
    "EventDescriber", "register", "get_describer", "list_describers",
    "describer_ids", "describe_meta", "MATURITY_LEVELS", "TRACE_SOURCES",
    "build_event_view", "view_from_row", "context_pad_samples",
    "estimate_i_open", "estimate_sigma_open", "estimate_blockade_baseline",
    "resolve_params", "describe_event", "describe_result",
    "describe_rows_compat", "cache_key", "cache_key_for", "view_for",
]
