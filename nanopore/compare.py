"""Pure comparison metrics shared by the GUI comparison dialog and reports.

Two independent comparisons live here, both Qt-free:

* detector boundaries — one-to-one overlap matching of kept-event spans and
  the median start/end displacement (the historical comparison CSV口径);
* describer output — per-describer segment counts, coverage and validity on
  the same events, so a describer can be compared without re-reading the ABF.

Keeping these out of the Qt module lets the CLI, tests and any future report
reuse exactly the same numbers.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def match_intervals(a: list[tuple[float, float]],
                    b: list[tuple[float, float]],
                    min_overlap: float = 0.5):
    """One-to-one overlap match; returns (pairs, unmatched_a, unmatched_b)."""
    a = sorted(a)
    b = sorted(b)
    pairs: list[tuple[int, int]] = []
    used: set[int] = set()
    j = 0
    for i, (as_, ae) in enumerate(a):
        while j < len(b) and b[j][1] <= as_:
            j += 1
        best = None
        k = j
        while k < len(b) and b[k][0] < ae:
            bs, be = b[k]
            ov = min(ae, be) - max(as_, bs)
            if ov > 0:
                score = min(ov / max(ae - as_, 1e-12), ov / max(be - bs, 1e-12))
                if best is None or score > best[0]:
                    best = (score, k)
            k += 1
        if best is not None and best[0] >= min_overlap and best[1] not in used:
            pairs.append((i, best[1]))
            used.add(best[1])
    return pairs, len(a) - len(pairs), len(b) - len(used)


def boundary_metrics(base: list[tuple[float, float]],
                     other: list[tuple[float, float]]) -> dict:
    """Agreement of ``other`` against ``base`` (both are kept-event spans)."""
    pairs, ua, ub = match_intervals(base, other)
    if not pairs:
        return {"matched": 0, "only_base": ua, "only_other": ub,
                "d_start_ms": float("nan"), "d_end_ms": float("nan"),
                "d_boundary_ms": float("nan")}
    ds = np.array([(other[j][0] - base[i][0]) * 1e3 for i, j in pairs])
    de = np.array([(other[j][1] - base[i][1]) * 1e3 for i, j in pairs])
    return {
        "matched": len(pairs),
        "only_base": ua,
        "only_other": ub,
        "d_start_ms": float(np.median(np.abs(ds))),
        "d_end_ms": float(np.median(np.abs(de))),
        "d_boundary_ms": float(np.median(np.concatenate((np.abs(ds), np.abs(de))))),
    }


@dataclass
class DescriberMetrics:
    """One describer's output on a common event set."""

    describer: str
    n_events: int = 0
    n_valid: int = 0
    median_segments: float = float("nan")
    total_segments: int = 0
    median_coverage: float = float("nan")
    elapsed_s: float = float("nan")

    def as_row(self) -> dict:
        return {
            "describer": self.describer,
            "n_events": self.n_events,
            "n_valid": self.n_valid,
            "median_segments": self.median_segments,
            "total_segments": self.total_segments,
            "median_coverage": self.median_coverage,
            "elapsed_s": self.elapsed_s,
        }


def describer_metrics(descs_by_id: dict[str, list],
                      elapsed_by_id: dict[str, float] | None = None
                      ) -> list[DescriberMetrics]:
    """Summarise each describer's descriptions on the same events."""
    elapsed_by_id = elapsed_by_id or {}
    out: list[DescriberMetrics] = []
    for did, descs in descs_by_id.items():
        descs = list(descs or [])
        valid = [d for d in descs
                 if bool((getattr(d, "quality", None) or {}).get("valid", True))]
        seg_counts = [len(getattr(d, "segments", None) or []) for d in valid]
        coverage = [float((getattr(d, "coverage", None) or {}).get("coverage_frac",
                                                                   float("nan")))
                    for d in valid]
        cov = [c for c in coverage if np.isfinite(c)]
        out.append(DescriberMetrics(
            describer=did,
            n_events=len(descs),
            n_valid=len(valid),
            median_segments=(float(np.median(seg_counts)) if seg_counts
                             else float("nan")),
            total_segments=int(sum(seg_counts)),
            median_coverage=(float(np.median(cov)) if cov else float("nan")),
            elapsed_s=float(elapsed_by_id.get(did, float("nan"))),
        ))
    return out
