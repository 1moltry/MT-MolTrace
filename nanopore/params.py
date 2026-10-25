"""Qt-free parameter metadata shared by detectors, describers and the GUI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ParamSpec:
    """Declarative parameter metadata for GUI/CLI generation (Qt-free)."""

    name: str
    default: Any
    kind: str = "float"            # float / int / bool / str / choice
    label: str = ""
    desc: str = ""
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[str, ...] = ()
