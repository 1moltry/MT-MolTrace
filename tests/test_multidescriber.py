"""Multi-describer analysis, comparison metrics and CLI surface."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np

from nanopore.io import AbfRecording
from tests.synth import SynthEvent, make_signal


def _rec() -> AbfRecording:
    sig = make_signal([SynthEvent(1.0, 0.05, -50.0)], duration_s=3.0,
                      sample_rate_hz=25_000.0, noise_sigma_pA=1.0, seed=11)
    return AbfRecording(path=Path("synthetic.abf"), current=sig.current,
                        sample_rate_hz=sig.sample_rate_hz, units="pA",
                        n_channels=1, sweep_count=1)


def test_analyze_computes_extra_describers():
    from nanopore.analyze import analyze
    from nanopore.config import PipelineConfig

    cfg = PipelineConfig(enabled_mods=("describe",), describer="dp_bic",
                         describers=("classic", "scalar"))
    res = analyze(_rec(), cfg)

    assert res.descs and res.descs[0].describer == "dp_bic"
    assert set(res.desc_extra) == {"classic", "scalar"}
    assert all(d.describer == "classic" for d in res.desc_extra["classic"])
    assert all(d.describer == "scalar" for d in res.desc_extra["scalar"])


def test_extra_describers_skip_the_primary_id():
    from nanopore.analyze import analyze
    from nanopore.config import PipelineConfig

    cfg = PipelineConfig(enabled_mods=("describe",), describer="dp_bic",
                         describers=("dp_bic", "scalar"))
    res = analyze(_rec(), cfg)
    assert set(res.desc_extra) == {"scalar"}


def test_describer_metrics_summarises_segments_and_coverage():
    from nanopore.compare import describer_metrics

    def desc(n, cov, valid=True):
        return SimpleNamespace(
            segments=[object()] * n,
            coverage={"coverage_frac": cov},
            quality={"valid": valid},
        )

    metrics = {
        "a": [desc(3, 0.9), desc(1, 0.7), desc(5, 0.5, valid=False)],
        "b": [desc(2, 1.0), desc(2, 0.8), desc(2, 0.6)],
    }
    rows = {m.describer: m for m in describer_metrics(metrics, {"a": 1.5})}

    assert rows["a"].n_events == 3 and rows["a"].n_valid == 2
    assert rows["a"].median_segments == 2.0
    assert rows["a"].total_segments == 4
    assert abs(rows["a"].median_coverage - 0.8) < 1e-12
    assert rows["a"].elapsed_s == 1.5
    assert rows["b"].median_segments == 2.0
    assert np.isnan(rows["b"].elapsed_s)


def test_cli_describe_choices_include_registered_describers():
    from nanopore.cli import build_parser
    from nanopore.fingerprint import describer_ids

    args = build_parser().parse_args(["run", "x.abf", "--describe", "classic"])
    assert args.describe == "classic"
    assert set(describer_ids()) >= {"dp_bic", "scalar", "classic"}


def test_cli_rejects_unknown_describers(capsys):
    from nanopore.cli import main

    code = main(["run", "missing.abf", "--describers", "dp_bic,nope"])
    assert code == 2
    assert "unknown describer" in capsys.readouterr().err.lower()
