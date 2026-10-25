"""Optional research dependencies.

The experimental shape layer uses ``ruptures`` (PELT change points) and
``scikit-learn`` (agglomerative clustering). Both live in the ``research``
extra. Importing this module never imports them: the guard is only consulted
when an experimental algorithm is actually run, so the production pipeline and
the GUI still start on a plain install.
"""
from __future__ import annotations

import importlib
import importlib.util

from ..registry import DescriberUnavailable

#: Distribution name -> import name used for the availability check.
REQUIRED: dict[str, str] = {
    "ruptures": "ruptures",
    "scikit-learn": "sklearn",
}

INSTALL_HINT = 'pip install -e ".[research]"'


class ResearchDependencyError(DescriberUnavailable):
    """Raised when an experimental algorithm is run without its extra."""


def missing_dependencies() -> list[str]:
    """Distribution names whose import is unavailable."""
    return [dist for dist, mod in REQUIRED.items()
            if importlib.util.find_spec(mod) is None]


def require_research() -> None:
    missing = missing_dependencies()
    if missing:
        raise ResearchDependencyError(
            "实验性形状研究缺少依赖：" + ", ".join(missing)
            + f"。请安装 research extra：{INSTALL_HINT}")


def require(module: str):
    """Import ``module`` or raise the same actionable error."""
    try:
        return importlib.import_module(module)
    except Exception as exc:  # noqa: BLE001 — surface one clear message
        raise ResearchDependencyError(
            f"实验性形状研究需要 {module}；请安装 research extra：{INSTALL_HINT}"
        ) from exc
