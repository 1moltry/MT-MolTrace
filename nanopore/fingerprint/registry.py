"""Describer registry: ids, maturity and parameter metadata.

Registration is an explicit import (see :mod:`nanopore.fingerprint.builtin`),
never entry-point discovery, so PyInstaller builds keep every describer.
"""
from __future__ import annotations

from typing import Any, Mapping

from ..params import ParamSpec

MATURITY_LEVELS: tuple[str, ...] = ("stable", "beta", "experimental")
TRACE_SOURCES: tuple[str, ...] = ("analysis", "raw")


class DescriberUnavailable(RuntimeError):
    """A describer cannot run yet (missing model, missing optional extra)."""


class EventDescriber:
    """Base class: set metadata and implement :meth:`describe`.

    ``maturity`` is an honesty label, not a UI flag: ``stable`` = interface and
    calibration are relied on in production; ``beta`` = usable but a known
    limitation is being worked on; ``experimental`` = research only and never
    enabled by default.
    """

    id: str = ""
    label: str = ""
    version: str = "1"
    maturity: str = "stable"
    input_trace: str = "analysis"
    params: tuple[ParamSpec, ...] = ()
    requires_model: bool = False
    data_prerequisites: tuple[str, ...] = ()

    def default_params(self) -> dict[str, Any]:
        return {p.name: p.default for p in self.params}

    def resolve_params(self, overrides: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Defaults overlaid with user overrides; unknown keys are dropped."""
        known = {p.name for p in self.params}
        out = self.default_params()
        for key, value in dict(overrides or {}).items():
            if key in known:
                out[key] = value
        return out

    def describe(self, view, params: Mapping[str, Any] | None = None):
        raise NotImplementedError

    def info(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "version": self.version,
            "maturity": self.maturity,
            "input_trace": self.input_trace,
            "requires_model": bool(getattr(self, "requires_model", False)),
            "data_prerequisites": list(getattr(self, "data_prerequisites", ())),
            "params": [
                {"name": p.name, "default": p.default, "kind": p.kind,
                 "label": p.label, "desc": p.desc,
                 "minimum": p.minimum, "maximum": p.maximum,
                 "choices": list(p.choices)}
                for p in self.params
            ],
        }


class CorpusShapeMethod(EventDescriber):
    """A describer that must be fitted on a cross-event corpus first.

    ``fit`` produces a model (e.g. a shape vocabulary); ``decode`` applies it
    to one :class:`~nanopore.fingerprint.EventView`. ``describe`` is only a
    fallback for the active model, so a registry entry cannot silently invent
    a vocabulary.
    """

    requires_model = True

    def fit(self, corpus, params: Mapping[str, Any] | None = None):
        raise NotImplementedError

    def decode(self, view, model, params: Mapping[str, Any] | None = None):
        raise NotImplementedError


_DESCRIBERS: dict[str, EventDescriber] = {}


def register(describer: EventDescriber) -> EventDescriber:
    if not describer.id:
        raise ValueError("describer.id must be non-empty")
    if describer.maturity not in MATURITY_LEVELS:
        raise ValueError(
            f"describer {describer.id!r}: maturity must be one of {MATURITY_LEVELS}")
    if describer.input_trace not in TRACE_SOURCES:
        raise ValueError(
            f"describer {describer.id!r}: input_trace must be one of {TRACE_SOURCES}")
    _DESCRIBERS[describer.id] = describer
    return describer


def get_describer(describer_id: str) -> EventDescriber:
    try:
        return _DESCRIBERS[describer_id]
    except KeyError:
        raise KeyError(
            f"unknown describer {describer_id!r}; available: "
            + ", ".join(sorted(_DESCRIBERS))
        ) from None


def list_describers() -> list[EventDescriber]:
    return [_DESCRIBERS[k] for k in sorted(_DESCRIBERS)]


def describer_ids() -> tuple[str, ...]:
    return tuple(sorted(_DESCRIBERS))


def describe_meta() -> list[dict[str, Any]]:
    """GUI-facing metadata for every registered describer."""
    return [d.info() for d in list_describers()]
