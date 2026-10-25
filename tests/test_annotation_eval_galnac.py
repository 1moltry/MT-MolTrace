"""Real-annotation regression: the classic baseline on GalNAc-1.

Uses the sugar project's frozen event table and the 12-event / 97-fingerprint
annotation. The data lives outside this repository, so the module skips when
it is absent (CI without the lab share). This is the phase 4 acceptance
metric: the classic dual-threshold describer must reproduce the published
F1@0.5 ms ≈ 0.53, and the BIC effective-sample-size diagnostic must reduce
the known over-segmentation of the source DP+BIC setting.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from nanopore.analyze import AnalysisResult
from nanopore.config import PipelineConfig
from nanopore.fingerprint import (describe_result, evaluate_intervals,
                                  to_global_intervals)

pytestmark = pytest.mark.integration

_SUGAR = Path(__file__).resolve().parents[2] / "糖测序-ML找指纹"
_ABF = _SUGAR / "信号" / "乙酰氨基半乳糖" / "GalNAc-1.abf"
_INDEX = _SUGAR / "sweeps_all" / "GalNAc-1_events_index.csv"
_ANN = _SUGAR / "annotations" / "GalNAc-1__1moltry__r1.csv"


def _fixture():
    from nanopore.io import read_abf

    if not (_ABF.exists() and _INDEX.exists() and _ANN.exists()):
        pytest.skip("GalNAc-1 annotation/event table not present locally")
    rec = read_abf(_ABF)
    events = pd.read_csv(_INDEX)
    ann = pd.read_csv(_ANN)
    ids = sorted(ann.loc[ann["kind"] == "fingerprint", "event_id"].unique())
    sub = events[events["event_id"].isin(ids)].sort_values("event_id").reset_index(drop=True)
    df = pd.DataFrame({
        "t1": sub["start_time_s"].astype(float),
        "t2": sub["end_time_s"].astype(float),
        "Io": sub["level0_ref_pA"].astype(float),
        "mean": sub["depth_pA"].astype(float),
        "state": sub["state"].astype(str),
    })
    truth = {
        int(eid): list(zip(g["cut_start_sample"].astype(int),
                           g["cut_end_sample"].astype(int)))
        for eid, g in ann[ann["kind"] == "fingerprint"].groupby("event_id")
    }
    return rec, sub, df, truth


def _run(rec, sub, df, truth, describer: str, params: dict):
    cfg = PipelineConfig(enabled_mods=("describe",), describer=describer,
                         describe_params=params)
    res = AnalysisResult(rec, None, rec.current, None, None, None, df, None,
                         detector_id="plateau", enabled_mods=("describe",),
                         config=cfg)
    descs = describe_result(res, cfg)
    pred = {int(eid): to_global_intervals(d)
            for eid, d in zip(sub["event_id"], descs)}
    return descs, evaluate_intervals(pred, truth, rec.sample_rate_hz,
                                     tols_ms=(0.25, 0.5, 1.0))


def test_classic_reproduces_the_published_baseline():
    rec, sub, df, truth = _fixture()
    descs, rep = _run(rec, sub, df, truth, "classic", {})
    summary = rep.summary()

    assert summary["n_truth"] == 97
    # Published baseline on this annotation: 112 candidates, F1@0.5 ≈ 0.536,
    # P ≈ 0.50, R ≈ 0.58, median displacement ≈ 0.36 / 0.32 ms.
    assert 90 <= summary["n_pred"] <= 140
    assert 0.45 <= summary["interval_F1@0.5ms"] <= 0.62
    assert 0.40 <= summary["interval_precision@0.5ms"] <= 0.60
    assert 0.48 <= summary["interval_recall@0.5ms"] <= 0.68
    assert summary["median_disp_start_ms"] <= 0.60
    assert summary["median_disp_end_ms"] <= 0.60
    # Classic fingerprints cover only the candidate intervals, so coverage is
    # the fraction of the body that is fingerprint (not a trimming fraction).
    assert all(0.0 <= d.coverage["coverage_frac"] <= 1.0 for d in descs)
    assert any(d.coverage["coverage_frac"] > 0.2 for d in descs)


def test_bic_effective_sample_size_reduces_the_known_over_segmentation():
    rec, sub, df, truth = _fixture()
    base, rep_base = _run(rec, sub, df, truth, "dp_bic", {"bic_n_eff": 0})
    auto, rep_auto = _run(rec, sub, df, truth, "dp_bic",
                          {"bic_n_eff": -1, "bic_penalty": 1.0})

    # The source setting over-segments this corpus (≈195 segments for 97
    # fingerprints). The autocorrelation-aware BIC is a diagnostic, not yet a
    # default: it reduces the count substantially but loses recall, so it stays
    # opt-in until the annotation corpus is large enough to calibrate it.
    assert rep_base.summary()["n_pred"] > 97 * 1.5
    assert rep_auto.summary()["n_pred"] < rep_base.summary()["n_pred"]
