"""Experimental research workspace (offscreen)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("PyQt5")
pytest.importorskip("pyqtgraph")
pytest.importorskip("ruptures")
pytest.importorskip("sklearn")

from PyQt5.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


def _corpus_and_model():
    from nanopore.analyze import AnalysisResult
    from nanopore.config import PipelineConfig
    from nanopore.fingerprint.research import EventCorpus, fit_vocabulary
    from nanopore.io import AbfRecording

    fs = 25_000.0
    rng = np.random.default_rng(0)
    n = 3_000 + 4 * 5_000
    current = 100.0 + rng.normal(0.0, 1.0, n)
    rows = []
    for k in range(4):
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
    corpus = EventCorpus.from_analysis(res)
    model = fit_vocabulary(corpus, {"pen_mult": 8.0, "min_support": 1,
                                    "cap": 30, "dist": "dtw", "n_iter_dba": 1})
    return corpus, model, cfg


def test_home_has_the_research_card(qapp):
    from nanopore.gui.home import HomeWindow

    win = HomeWindow()
    try:
        assert "指纹研究" in win.card_research.text()
        assert "实验性" in win.card_research.text()
    finally:
        win.close()


def test_research_dialog_is_explicit_about_its_status(qapp):
    from nanopore.config import PipelineConfig
    from nanopore.gui.research import ResearchDialog

    dlg = ResearchDialog(PipelineConfig())
    try:
        assert dlg.tabs.count() == 3
        assert "0.674" in dlg.warn_label.text()
        assert "0.85" in dlg.warn_label.text()
        assert not dlg.btn_fit.isEnabled()      # no corpus yet
        assert not dlg.btn_decode.isEnabled()
    finally:
        dlg.close()


def test_model_populates_table_and_thumbnails(qapp):
    from nanopore.config import PipelineConfig
    from nanopore.gui.research import ResearchDialog

    corpus, model, _cfg = _corpus_and_model()
    dlg = ResearchDialog(PipelineConfig())
    try:
        dlg._on_corpus(corpus)
        assert dlg.event_combo.count() == corpus.n_events
        assert dlg.btn_fit.isEnabled()
        dlg._on_model(model)
        assert dlg.model_table.rowCount() == len(model.centers)
        assert dlg.thumb_grid.count() > 0
        assert dlg.btn_decode.isEnabled()
    finally:
        dlg.close()


def test_decode_draws_the_overlay(qapp):
    from nanopore.config import PipelineConfig
    from nanopore.gui.research import ResearchDialog

    corpus, model, _cfg = _corpus_and_model()
    dlg = ResearchDialog(PipelineConfig())
    try:
        dlg._on_corpus(corpus)
        dlg._on_model(model)
        dlg.event_combo.setCurrentIndex(0)
        dlg._decode()
        assert dlg.decode_table.rowCount() >= 1
        assert model.model_id in dlg.decode_label.text()
        assert len(dlg.decode_plot.listDataItems()) >= 1
    finally:
        dlg.close()


def test_missing_dependencies_disable_fit_and_decode(qapp, monkeypatch):
    from nanopore.config import PipelineConfig
    from nanopore.gui import research as research_mod

    corpus, model, _cfg = _corpus_and_model()
    monkeypatch.setattr(research_mod, "missing_dependencies",
                        lambda: ["ruptures"])
    dlg = research_mod.ResearchDialog(PipelineConfig())
    try:
        assert "缺少" in dlg.dep_label.text()
        dlg._on_corpus(corpus)
        dlg._on_model(model)
        assert not dlg.btn_fit.isEnabled()
        assert not dlg.btn_decode.isEnabled()
    finally:
        dlg.close()
