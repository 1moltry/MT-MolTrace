"""Experimental shape vocabulary: fit, decode, persistence, registry honesty."""

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


def _analysis(n_events: int = 6, seed: int = 0):
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


def _fit_params():
    return {"pen_mult": 8.0, "min_support": 1, "cap": 50,
            "dist": "dtw", "min_frag_ms": 0.5, "n_iter_dba": 2}


def test_registry_marks_the_research_describers_experimental():
    from nanopore.fingerprint import describe_meta, get_describer

    for did in ("shape_vocab", "pelt"):
        d = get_describer(did)
        assert d.maturity == "experimental"
        assert d.params
        info = next(i for i in describe_meta() if i["id"] == did)
        assert info["maturity"] == "experimental"
    assert get_describer("shape_vocab").requires_model is True
    assert get_describer("pelt").requires_model is False


def test_fit_decode_save_load_roundtrip(tmp_path):
    from nanopore.fingerprint.research import (EventCorpus, ShapeModel,
                                               decode_corpus,
                                               fit_vocabulary)

    corpus = EventCorpus.from_analysis(_analysis())
    model = fit_vocabulary(corpus, _fit_params())

    assert model.method == "shape_vocab"
    assert model.centers and len(model.centers) == len(model.support)
    assert model.metadata["experimental"] is True
    assert "0.674" in model.metadata["gate_note"]
    assert "0.85" in model.metadata["gate_note"]

    descs = decode_corpus(corpus, model)
    assert len(descs) == corpus.n_events
    d = descs[0]
    assert d.quality["valid"] is True
    assert d.quality["experimental"] is True
    assert d.segments
    assert d.payload["experimental"] is True

    path = model.save(tmp_path / "vocab.json")
    loaded = ShapeModel.load(path)
    assert loaded.model_id == model.model_id
    assert len(loaded.centers) == len(model.centers)
    assert np.allclose(loaded.centers[0], model.centers[0])


def test_shape_vocab_without_an_active_model_reports_a_reason():
    from nanopore.fingerprint import (clear_active_model, describe_result,
                                      get_describer, set_active_model)
    from nanopore.fingerprint.research import EventCorpus, fit_vocabulary

    res = _analysis()
    cfg = res.config
    clear_active_model("shape_vocab")
    desc = describe_result(res, cfg, describer_id="shape_vocab")[0]
    assert desc.quality["valid"] is False
    assert "词表" in desc.quality["reason"]
    assert desc.segments == []

    corpus = EventCorpus.from_analysis(res)
    model = fit_vocabulary(corpus, _fit_params())
    set_active_model(model)
    ok = describe_result(res, cfg, describer_id="shape_vocab")[0]
    assert ok.quality["valid"] is True
    assert ok.segments


def test_pelt_describer_finds_the_two_levels():
    from nanopore.fingerprint import describe_result

    res = _analysis(n_events=1)
    cfg = res.config
    desc = describe_result(res, cfg, describer_id="pelt")[0]
    assert desc.quality["valid"] is True
    assert desc.quality["experimental"] is True
    assert len(desc.segments) >= 2
    assert desc.features["n_fragments"] == float(len(desc.segments))


def test_missing_dependency_error_is_actionable(monkeypatch):
    from nanopore.fingerprint import DescriberUnavailable
    from nanopore.fingerprint.research import deps

    monkeypatch.setattr(deps, "missing_dependencies", lambda: ["ruptures"])
    with pytest.raises(DescriberUnavailable) as info:
        deps.require_research()
    assert "research" in str(info.value)
    assert "ruptures" in str(info.value)
