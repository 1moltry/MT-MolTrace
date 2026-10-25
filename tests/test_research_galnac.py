"""Real GalNAc-1 smoke test for the experimental shape workspace.

Uses the sugar project's frozen event table and annotation-adjacent events, so
it exercises real bodies without depending on MolTrace's detector. Skips when
the external data is absent (CI without the lab share).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from nanopore.analyze import AnalysisResult
from nanopore.config import PipelineConfig
from nanopore.fingerprint.research import (EventCorpus, ShapeModel,
                                           decode_corpus, fit_vocabulary,
                                           null_report)

pytestmark = pytest.mark.integration

pytest.importorskip("ruptures")
pytest.importorskip("sklearn")

_SUGAR = Path(__file__).resolve().parents[2] / "糖测序-ML找指纹"
_ABF = _SUGAR / "信号" / "乙酰氨基半乳糖" / "GalNAc-1.abf"
_INDEX = _SUGAR / "sweeps_all" / "GalNAc-1_events_index.csv"
_ANN = _SUGAR / "annotations" / "GalNAc-1__1moltry__r1.csv"


def _fixture(n_events: int = 6):
    from nanopore.io import read_abf

    if not (_ABF.exists() and _INDEX.exists() and _ANN.exists()):
        pytest.skip("GalNAc-1 data not present locally")
    rec = read_abf(_ABF)
    events = pd.read_csv(_INDEX)
    ann = pd.read_csv(_ANN)
    ids = sorted(ann.loc[ann["kind"] == "fingerprint", "event_id"].unique())
    sub = events[events["event_id"].isin(ids)].sort_values("event_id").head(n_events)
    df = pd.DataFrame({
        "t1": sub["start_time_s"].astype(float),
        "t2": sub["end_time_s"].astype(float),
        "Io": sub["level0_ref_pA"].astype(float),
        "mean": sub["depth_pA"].astype(float),
        "state": sub["state"].astype(str),
    }).reset_index(drop=True)
    cfg = PipelineConfig(enabled_mods=("describe",), describer="shape_vocab")
    res = AnalysisResult(rec, None, rec.current, None, None, None, df, None,
                         detector_id="plateau", enabled_mods=("describe",),
                         config=cfg)
    return res


def test_fit_decode_on_real_event_bodies(tmp_path):
    res = _fixture(6)
    corpus = EventCorpus.from_analysis(res)
    assert corpus.n_events == 6

    params = {"pen_mult": 16.0, "min_support": 1, "cap": 40,
              "dist": "dtw", "min_frag_ms": 1.0, "n_iter_dba": 1}
    model = fit_vocabulary(corpus, params)
    assert model.centers
    assert model.metadata["experimental"] is True

    descs = decode_corpus(corpus, model)
    assert len(descs) == corpus.n_events
    assert any(d.segments for d in descs)
    assert all(d.quality.get("experimental") for d in descs)

    path = model.save(tmp_path / "galnac_vocab.json")
    loaded = ShapeModel.load(path)
    assert loaded.model_id == model.model_id


def test_null_report_runs_on_real_events():
    res = _fixture(3)
    corpus = EventCorpus.from_analysis(res)
    model = fit_vocabulary(corpus, {
        "pen_mult": 16.0, "min_support": 1, "cap": 20,
        "dist": "dtw", "min_frag_ms": 1.0, "n_iter_dba": 1})
    report = null_report(corpus, model, max_events=3, seed=0)
    assert report["n_events"] == 3
    assert "0.674" in report["gate_note"]
    assert set(report["recurrence"]) == {"real", "N1flat", "N1tele", "N2phase"}
