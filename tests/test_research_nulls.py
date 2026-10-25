"""Null models and leave-one-file diagnostics for shape research."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("ruptures")
pytest.importorskip("sklearn")

from nanopore.analyze import AnalysisResult
from nanopore.config import PipelineConfig
from nanopore.io import AbfRecording


def _analysis(n_events: int = 3, seed: int = 1):
    fs = 25_000.0
    rng = np.random.default_rng(seed)
    n = 3_000 + n_events * 5_000
    current = 100.0 + rng.normal(0.0, 1.0, n)
    rows = []
    for k in range(n_events):
        s = 3_000 + k * 5_000
        e = s + 2_000
        current[s:e] = 60.0 + rng.normal(0.0, 1.0, e - s)
        current[s + 800:e] = 40.0 + rng.normal(0.0, 1.0, e - s - 800)
        rows.append({"t1": s / fs, "t2": e / fs, "Io": 100.0,
                     "mean": -50.0, "state": "A"})
    rec = AbfRecording(path=Path("synthetic.abf"), current=current,
                       sample_rate_hz=fs, units="pA", n_channels=1,
                       sweep_count=1)
    cfg = PipelineConfig(enabled_mods=("describe",), describer="shape_vocab")
    res = AnalysisResult(rec, None, current, None, None, None,
                         pd.DataFrame(rows), None, detector_id="level",
                         enabled_mods=("describe",), config=cfg)
    return res


def _model(corpus):
    from nanopore.fingerprint.research import fit_vocabulary

    return fit_vocabulary(corpus, {
        "pen_mult": 8.0, "min_support": 1, "cap": 30,
        "dist": "dtw", "n_iter_dba": 1,
    })


def test_auc_direction():
    from nanopore.fingerprint.research import auc

    assert auc(np.array([0.1, 0.2]), np.array([1.0, 2.0])) == pytest.approx(1.0)
    assert auc(np.array([2.0, 3.0]), np.array([0.1, 0.2])) == pytest.approx(0.0)
    assert np.isnan(auc(np.array([]), np.array([1.0])))


def test_null_report_runs_and_is_explicitly_experimental():
    from nanopore.fingerprint.research import EventCorpus, null_report

    corpus = EventCorpus.from_analysis(_analysis())
    model = _model(corpus)
    report = null_report(corpus, model, max_events=3, seed=0)

    assert report["n_events"] == 3
    assert report["model_id"] == model.model_id
    assert "0.674" in report["gate_note"] and "0.85" in report["gate_note"]
    for key in ("auc_real_vs_N1flat", "auc_real_vs_N1tele",
                "auc_real_vs_N2phase"):
        assert key in report
        value = report[key]
        assert np.isnan(value) or 0.0 <= value <= 1.0
    assert set(report["recurrence"]) == {"real", "N1flat", "N1tele", "N2phase"}


def test_leave_one_file_needs_at_least_two_sources():
    from nanopore.fingerprint.research import EventCorpus, leave_one_file

    corpus = EventCorpus.from_analysis(_analysis())
    report = leave_one_file(corpus, None)
    assert report["status"] == "insufficient_sources"
    assert report["n_sources"] == 1
